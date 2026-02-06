"""
LLM evaluation tasks using LangChain.

Evaluates videos against topic criteria, generates video summaries,
and returns structured results.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from prefect import task

from config import (
    ANTHROPIC_API_KEY,
    DEFAULT_LLM_MODEL,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
    TRANSCRIPT_MAX_CHARS,
)
from models.schemas import (
    Criterion,
    CriterionResultCreate,
    CriterionResultValue,
    GoldStandardWithContext,
    VideoData,
)

logger = logging.getLogger(__name__)


# ── Structured output schema ─────────────────────────────────


class CriterionEvaluation(BaseModel):
    """Structured output from the LLM for criterion evaluation."""

    result: Literal["PASS", "FAIL", "CANNOT_TELL"] = Field(
        description=(
            "PASS if the video clearly meets the criterion, "
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
You are a video content evaluator. Your job is to assess whether a YouTube video meets a specific criterion based on the video's metadata and transcript.

You must respond with one of three results:
- PASS: The video clearly meets the criterion.
- FAIL: The video clearly does NOT meet the criterion.
- CANNOT_TELL: There is not enough information to determine whether the video meets the criterion.

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

## Criterion to Evaluate
{condition}
---

Evaluate whether this video meets the above criterion. Provide your result (PASS, FAIL, or CANNOT_TELL) and a brief explanation.
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

## Criterion to Evaluate
{condition}
---

Evaluate whether this video meets the above criterion. Provide your result (PASS, FAIL, or CANNOT_TELL) and a brief explanation.
""".strip()


def _build_few_shot_messages(
    examples: list[tuple[GoldStandardWithContext, VideoData]],
    criterion: Criterion,
    current_video_id: str,
) -> list[tuple[str, str]]:
    """
    Build few-shot human/AI message pairs from gold standard examples.

    Each pair consists of:
    - Human message: video info (with summary instead of transcript) + criterion
    - AI message: expected CriterionEvaluation JSON

    Filters out the current video being evaluated if it happens to be
    a gold standard itself.
    """
    messages: list[tuple[str, str]] = []

    for gs, video_data in examples:
        # Skip the current video being evaluated
        if video_data.video_id == current_video_id:
            continue

        # Build human message with concrete values
        summary_text = video_data.summary or gs.video_summary or "(No summary available)"

        human_msg = FEW_SHOT_HUMAN_TEMPLATE.format(
            title=video_data.title,
            channel=video_data.channel_title,
            description=video_data.description[:2000] if video_data.description else "",
            tags=", ".join(video_data.tags[:30]) if video_data.tags else "(none)",
            duration=str(video_data.duration_seconds),
            views=str(video_data.view_count),
            summary=summary_text,
            condition=criterion.condition,
        )

        # Build AI message — derive result from gold standard polarity
        result = "PASS" if gs.is_positive else "FAIL"
        if gs.note:
            explanation = gs.note
        else:
            explanation = (
                f"The video {'meets' if gs.is_positive else 'does not meet'} "
                f"the criterion based on its content."
            )

        ai_msg = json.dumps({"result": result, "explanation": explanation})

        messages.append(("human", human_msg))
        messages.append(("ai", ai_msg))

    return messages


# ── Evaluation task ───────────────────────────────────────────


@task(name="evaluate_criterion", retries=2, retry_delay_seconds=15)
def evaluate_criterion(
    video: VideoData,
    criterion: Criterion,
    model_name: str | None = None,
    few_shot_examples: list[tuple[GoldStandardWithContext, VideoData]] | None = None,
) -> CriterionResultCreate:
    """
    Evaluate a single criterion against a video using an LLM.

    If few_shot_examples are provided, they are prepended as human/AI
    turn pairs (derived from gold standard videos) before the actual
    evaluation message, giving the model concrete examples.

    Returns a CriterionResultCreate ready to be saved to the DB.
    """
    llm, used_model = _get_llm(model_name)

    # Truncate transcript if too long
    transcript_text = video.transcript or "(No transcript available)"
    if len(transcript_text) > TRANSCRIPT_MAX_CHARS:
        transcript_text = (
            transcript_text[:TRANSCRIPT_MAX_CHARS]
            + "\n\n... [transcript truncated] ..."
        )

    # Build prompt: system + optional few-shot pairs + human
    if few_shot_examples:
        few_shot_msgs = _build_few_shot_messages(
            few_shot_examples, criterion, video.video_id,
        )
        prompt_messages: list[tuple[str, str]] = [
            ("system", EVALUATION_SYSTEM_PROMPT),
            *few_shot_msgs,
            ("human", EVALUATION_HUMAN_PROMPT),
        ]
        prompt = ChatPromptTemplate.from_messages(prompt_messages)
    else:
        prompt = EVALUATION_PROMPT

    # Build the chain with structured output and a descriptive trace name
    chain = (
        prompt | llm.with_structured_output(CriterionEvaluation)
    ).with_config(run_name="criterion_evaluation_chain")

    criterion_type_short = "INCLUDE" if criterion.include else "EXCLUDE"

    # LangSmith tracing config: descriptive name, metadata, and tags
    langsmith_config = RunnableConfig(
        run_name=f"eval | {video.title[:50]} | {criterion.condition[:40]}",
        metadata={
            "video_id": video.video_id,
            "video_title": video.title,
            "channel": video.channel_title,
            "criterion_id": criterion.id,
            "criterion_condition": criterion.condition,
            "criterion_type": criterion_type_short,
            "criterion_level": criterion.level,
            "model_name": used_model,
        },
        tags=["evaluation", "video-pipeline", criterion_type_short, used_model],
    )

    try:
        result: CriterionEvaluation = chain.invoke(
            {
                "title": video.title,
                "channel": video.channel_title,
                "description": video.description[:2000] if video.description else "",
                "tags": ", ".join(video.tags[:30]) if video.tags else "(none)",
                "duration": str(video.duration_seconds),
                "views": str(video.view_count),
                "transcript": transcript_text,
                "condition": criterion.condition,
            },
            config=langsmith_config,
        )

        return CriterionResultCreate(
            video_id=video.video_id,
            criterion_id=criterion.id,
            result=CriterionResultValue(result.result),
            explanation=result.explanation,
            model_used=used_model,
        )

    except Exception:
        logger.exception(
            "LLM evaluation failed for video=%s criterion=%s",
            video.video_id,
            criterion.id,
        )
        return CriterionResultCreate(
            video_id=video.video_id,
            criterion_id=criterion.id,
            result=CriterionResultValue.CANNOT_TELL,
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


@task(name="generate_summary", retries=2, retry_delay_seconds=15)
def generate_summary(
    video: VideoData,
    model_name: str | None = None,
) -> str | None:
    """
    Generate a concise summary of a video using an LLM.

    Returns the summary text, or None if generation fails.
    """
    llm, used_model = _get_llm(model_name)

    # Truncate transcript if too long
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
