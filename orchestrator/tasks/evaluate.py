"""
LLM evaluation tasks using LangChain.

Evaluates videos against ClassNode descriptions, generates video summaries,
and returns structured results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from prefect import task
from prefect.states import State

from config import (
    ANTHROPIC_API_KEY,
    DEFAULT_LLM_MODEL,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
    TRANSCRIPT_MAX_CHARS,
)
from utils.failed_queue import get_failed_queue
from utils.rate_limiter import get_rate_limiter
from models.schemas import (
    ClassNodeResultCreate,
    ClassNodeResultValue,
    ClassNodeWithRelations,
    GoldStandardWithContext,
    VideoData,
)

logger = logging.getLogger(__name__)


# ── Rate limit helpers ────────────────────────────────────────


def _llm_api_name(model_name: str) -> str:
    """Map a model name to its rate-limiter API key."""
    if model_name.startswith("claude"):
        return "anthropic"
    if model_name.startswith("gemini"):
        return "google"
    return "openai"


def _should_retry_llm(task, task_run, state: State) -> bool:
    """Retry only on rate-limit or transient connection errors."""
    exc = state.result(raise_on_failure=False)
    # Lazily resolve provider error types to avoid hard import at module load
    transient_names = {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "ServiceUnavailableError",
        "OverloadedError",
    }
    return type(exc).__name__ in transient_names or isinstance(
        exc, (ConnectionError, TimeoutError, OSError)
    )


def _on_evaluate_class_node_failure(task, task_run, state) -> None:
    """Push exhausted evaluate_class_node failures to the dead-letter queue."""
    exc = state.result(raise_on_failure=False)
    params = task_run.parameters or {}
    try:
        video = params.get("video")
        class_node = params.get("class_node")
        get_failed_queue("evaluate_class_node").push(
            {
                "video_id": video.video_id if video else None,
                "class_node_id": class_node.id if class_node else None,
                "model_name": params.get("model_name"),
                "error": str(exc),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        logger.exception(
            "Failed to push evaluate_class_node failure to dead-letter queue"
        )


# ── Structured output schema ─────────────────────────────────


class ClassNodeEvaluation(BaseModel):
    """Structured output from the LLM for class node evaluation."""

    result: Literal["PASS", "FAIL", "CANNOT_TELL"] = Field(
        description=(
            "PASS if the video clearly belongs to this class, "
            "FAIL if it clearly does not, "
            "CANNOT_TELL if there is insufficient information to determine."
        )
    )
    explanation: str = Field(
        description="Brief explanation (1-3 sentences) of why this result was chosen."
    )


# ── LLM factory ──────────────────────────────────────────────


def _get_llm(model_name: str | None = None) -> tuple[BaseChatModel, str]:
    """
    Create a LangChain chat model based on the model name.
    Returns (model, model_name_used).
    """
    model_name = model_name or DEFAULT_LLM_MODEL

    if model_name.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for Claude models")
        return ChatAnthropic(
            model=model_name,
            api_key=ANTHROPIC_API_KEY,
            max_tokens=1024,
        ), model_name

    elif model_name.startswith("gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required for Gemini models")
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GOOGLE_API_KEY,
        ), model_name

    else:
        # Default: OpenAI (gpt-4o, gpt-4o-mini, etc.)
        from langchain_openai import ChatOpenAI

        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for OpenAI models")
        return ChatOpenAI(
            model=model_name,
            api_key=OPENAI_API_KEY,
            max_tokens=1024,
        ), model_name


# ── Evaluation prompt ─────────────────────────────────────────


EVALUATION_SYSTEM_PROMPT = """
You are a video content classifier. Your job is to assess whether a YouTube video belongs to a specific content class based on the video's metadata and transcript.

You must respond with one of three results:
- PASS: The video clearly belongs to this class.
- FAIL: The video clearly does NOT belong to this class.
- CANNOT_TELL: There is not enough information to determine whether the video belongs to this class.

Be objective and base your assessment only on the provided information.
""".strip()

EVALUATION_HUMAN_PROMPT = """
## Video Information

**Title:** {title}

**Channel:** {channel}

**Description:**
{description}

**Tags:** {tags}

**Duration:** {duration} seconds

**Views:** {views}

**Transcript:**
{transcript}

---

## Class to Evaluate

{class_description}

---

Evaluate whether this video belongs to the above class. Provide your result (PASS, FAIL, or CANNOT_TELL) and a brief explanation.
""".strip()

EVALUATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EVALUATION_SYSTEM_PROMPT),
        ("human", EVALUATION_HUMAN_PROMPT),
    ]
)


# ── Few-shot helpers ──────────────────────────────────────────

FEW_SHOT_HUMAN_TEMPLATE = """
## Video Information

**Title:** {title}

**Channel:** {channel}

**Description:**
{description}

**Tags:** {tags}

**Duration:** {duration} seconds

**Views:** {views}

**Summary:**
{summary}

---

## Class to Evaluate

{class_description}

---

Evaluate whether this video belongs to the above class. Provide your result (PASS, FAIL, or CANNOT_TELL) and a brief explanation.
""".strip()


def _build_few_shot_messages(
    examples: list[tuple[GoldStandardWithContext, VideoData]],
    class_node: ClassNodeWithRelations,
    current_video_id: str,
) -> list[tuple[str, str]]:
    """
    Build few-shot human/AI message pairs from gold standard examples.

    Each pair consists of:
    - Human message: video info (with summary instead of transcript) + class description
    - AI message: expected ClassNodeEvaluation JSON

    Filters out the current video being evaluated if it happens to be
    a gold standard itself.
    """
    messages: list[tuple[str, str]] = []

    for gs, video_data in examples:
        if video_data.video_id == current_video_id:
            continue

        summary_text = video_data.summary or gs.video_summary or "(No summary available)"

        human_msg = FEW_SHOT_HUMAN_TEMPLATE.format(
            title=video_data.title,
            channel=video_data.channel_title,
            description=video_data.description[:2000] if video_data.description else "",
            tags=", ".join(video_data.tags[:30]) if video_data.tags else "(none)",
            duration=str(video_data.duration_seconds),
            views=str(video_data.view_count),
            summary=summary_text,
            class_description=class_node.description,
        )

        result = "PASS" if gs.is_positive else "FAIL"
        if gs.note:
            explanation = gs.note
        else:
            explanation = (
                f"The video {'belongs to' if gs.is_positive else 'does not belong to'} "
                f"this class based on its content."
            )

        ai_msg = json.dumps({"result": result, "explanation": explanation})

        messages.append(("human", human_msg))
        messages.append(("ai", ai_msg))

    return messages


# ── Evaluation task ───────────────────────────────────────────


@task(
    name="evaluate_class_node",
    retries=4,
    retry_delay_seconds=[15, 30, 60, 120],
    retry_jitter_factor=0.3,
    retry_condition_fn=_should_retry_llm,
    on_failure=[_on_evaluate_class_node_failure],
)
def evaluate_class_node(
    video: VideoData,
    class_node: ClassNodeWithRelations,
    model_name: str | None = None,
    few_shot_examples: list[tuple[GoldStandardWithContext, VideoData]] | None = None,
) -> ClassNodeResultCreate:
    """
    Evaluate whether a video belongs to a given ClassNode using an LLM.

    If few_shot_examples are provided, they are prepended as human/AI turn pairs
    (derived from gold standard videos) before the actual evaluation message.

    Returns a ClassNodeResultCreate ready to be saved to the DB.
    """
    llm, used_model = _get_llm(model_name)

    transcript_text = video.transcript or "(No transcript available)"
    if len(transcript_text) > TRANSCRIPT_MAX_CHARS:
        transcript_text = (
            transcript_text[:TRANSCRIPT_MAX_CHARS]
            + "\n\n... [transcript truncated] ..."
        )

    if few_shot_examples:
        few_shot_msgs = _build_few_shot_messages(
            few_shot_examples, class_node, video.video_id,
        )

        prompt_messages: list[tuple[str, str]] = [
            ("system", EVALUATION_SYSTEM_PROMPT),
            *few_shot_msgs,
            ("human", EVALUATION_HUMAN_PROMPT),
        ]
        prompt = ChatPromptTemplate.from_messages(prompt_messages)
    else:
        prompt = EVALUATION_PROMPT

    chain = (
        prompt | llm.with_structured_output(ClassNodeEvaluation)
    ).with_config(run_name="class_node_evaluation_chain")

    langsmith_config = RunnableConfig(
        run_name=f"eval | {video.title[:50]} | {class_node.description[:40]}",
        metadata={
            "video_id": video.video_id,
            "video_title": video.title,
            "channel": video.channel_title,
            "class_node_id": class_node.id,
            "class_node_description": class_node.description,
            "model_name": used_model,
        },
        tags=["evaluation", "video-pipeline", used_model],
    )

    get_rate_limiter(_llm_api_name(used_model)).acquire()

    try:
        result: ClassNodeEvaluation = chain.invoke(
            {
                "title": video.title,
                "channel": video.channel_title,
                "description": video.description[:2000] if video.description else "",
                "tags": ", ".join(video.tags[:30]) if video.tags else "(none)",
                "duration": str(video.duration_seconds),
                "views": str(video.view_count),
                "transcript": transcript_text,
                "class_description": class_node.description,
            },
            config=langsmith_config,
        )

        class_node_result = ClassNodeResultCreate(
            video_id=video.video_id,
            class_node_id=class_node.id,
            result=ClassNodeResultValue(result.result),
            explanation=result.explanation,
            model_used=used_model,
        )
        logger.info(
            "Evaluated class_node for video=%s class_node=%s result=%s model=%s",
            video.video_id,
            class_node.id,
            result.result,
            used_model,
        )
        return class_node_result

    except Exception:
        logger.exception(
            "LLM evaluation failed for video=%s class_node=%s",
            video.video_id,
            class_node.id,
        )
        return ClassNodeResultCreate(
            video_id=video.video_id,
            class_node_id=class_node.id,
            result=ClassNodeResultValue.CANNOT_TELL,
            explanation="Evaluation failed due to an error.",
            model_used=used_model,
        )


# ── Summary generation ────────────────────────────────────────


class VideoSummary(BaseModel):
    """Structured output from the LLM for video summary generation."""

    summary: str = Field(
        description=(
            "A concise summary (3-5 sentences) of the video's content, "
            "covering the main topics discussed, key takeaways, and "
            "the overall purpose of the video."
        )
    )


SUMMARY_SYSTEM_PROMPT = """
You are a video content summarizer. Your job is to produce a concise, informative summary of a YouTube video based on its metadata and transcript.

Guidelines:
- Write 3-5 sentences that capture the main topics, key points, and overall purpose.
- Be factual and objective — do not inject opinions or recommendations.
- If the transcript is unavailable, base your summary on the title, description, and tags.
- Write in third person (e.g. "The video covers…", "The creator explains…").
""".strip()

SUMMARY_HUMAN_PROMPT = """
## Video Information

**Title:** {title}

**Channel:** {channel}

**Description:**
{description}

**Tags:** {tags}

**Duration:** {duration} seconds

**Transcript:**
{transcript}

---

Provide a concise summary of this video.
""".strip()

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM_PROMPT),
        ("human", SUMMARY_HUMAN_PROMPT),
    ]
)


@task(
    name="generate_summary",
    retries=4,
    retry_delay_seconds=[15, 30, 60, 120],
    retry_jitter_factor=0.3,
    retry_condition_fn=_should_retry_llm,
)
def generate_summary(
    video: VideoData,
    model_name: str | None = None,
) -> str | None:
    """
    Generate a concise summary of a video using an LLM.

    Returns the summary text, or None if generation fails.
    """
    llm, used_model = _get_llm(model_name)

    transcript_text = video.transcript or "(No transcript available)"
    if len(transcript_text) > TRANSCRIPT_MAX_CHARS:
        transcript_text = (
            transcript_text[:TRANSCRIPT_MAX_CHARS]
            + "\n\n... [transcript truncated] ..."
        )

    chain = (
        SUMMARY_PROMPT | llm.with_structured_output(VideoSummary)
    ).with_config(run_name="video_summary_chain")

    langsmith_config = RunnableConfig(
        run_name=f"summary | {video.title[:50]}",
        metadata={
            "video_id": video.video_id,
            "video_title": video.title,
            "channel": video.channel_title,
            "model_name": used_model,
        },
        tags=["summary", "video-pipeline", used_model],
    )

    get_rate_limiter(_llm_api_name(used_model)).acquire()

    try:
        result: VideoSummary = chain.invoke(
            {
                "title": video.title,
                "channel": video.channel_title,
                "description": video.description[:2000] if video.description else "",
                "tags": ", ".join(video.tags[:30]) if video.tags else "(none)",
                "duration": str(video.duration_seconds),
                "transcript": transcript_text,
            },
            config=langsmith_config,
        )
        logger.info("Generated summary for video %s", video.video_id)
        return result.summary

    except Exception:
        logger.exception(
            "Summary generation failed for video=%s", video.video_id
        )
        return None
