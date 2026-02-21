"""
Inference API route.

POST /inference -- Generate a review using a trained model.
Called by both Application and Orchestrator.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from server.db import get_active_model, get_training_run
from server.models import (
    InferenceRequest,
    InferenceResponse,
    TrainingStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["inference"])


@router.post("/inference", response_model=InferenceResponse)
async def run_inference(request: InferenceRequest) -> InferenceResponse:
    """
    Generate a review using a trained innie model.

    Can be called with either:
    - modelName (explicit model)
    - topicId + method (looks up the active model)
    """
    checkpoint_path: str | None = None
    model_name: str | None = None

    if request.model_name:
        # Look up by explicit model name
        from server.db import list_models

        models = list_models()
        match = next((m for m in models if m.model_name == request.model_name), None)
        if not match:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{request.model_name}' not found",
            )
        if match.status != TrainingStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{request.model_name}' is not ready (status: {match.status})",
            )
        checkpoint_path = match.checkpoint_path
        model_name = match.model_name

    elif request.topic_id and request.method:
        # Look up active model for topic + method
        active = get_active_model(request.topic_id, request.method)
        if not active:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No active {request.method.value} model found "
                    f"for topic {request.topic_id}"
                ),
            )
        checkpoint_path = active.checkpoint_path
        model_name = active.model_name

    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'modelName' or both 'topicId' and 'method'",
        )

    if not checkpoint_path:
        raise HTTPException(
            status_code=500,
            detail=f"Model '{model_name}' has no checkpoint path",
        )

    # Run inference via Tinker
    try:
        review = await _sample_from_checkpoint(
            checkpoint_path=checkpoint_path,
            transcript=request.transcript,
            video_title=request.video_title,
        )
    except Exception as e:
        logger.exception("Inference failed for model %s", model_name)
        raise HTTPException(
            status_code=500,
            detail=f"Inference failed: {e}",
        )

    return InferenceResponse(review=review, modelName=model_name)


async def _sample_from_checkpoint(
    *,
    checkpoint_path: str,
    transcript: str,
    video_title: str | None = None,
) -> str:
    """Sample from a Tinker checkpoint to generate a review."""
    import tinker

    SYSTEM_PROMPT = """
Write a realistic review comment someone would leave after watching the talk.

IMPORTANT:
- Be specific, technical where appropriate, and grounded in the provided content.
- Be colloquial.
- Do not use markdown formatting. Just use plain text.
- Do not use preamble like "Here's my review..." or "Review:". Just write the review directly and finish it when you're done.
- Don't ramble. Be succint. Aim to not exceed 400 words.
- Break the review in multiple paragraphs with double newlines.
""".strip()

    user_content_parts = []
    if video_title:
        user_content_parts.append(f"Title:\n{video_title}")

    # Truncate transcript for prompt
    max_chars = 20_000
    t = transcript.replace("\r\n", "\n").replace("\r", "\n")
    if len(t) > max_chars:
        t = t[:max_chars] + "...[TRUNCATED]..."
    user_content_parts.append(f"Transcript:\n{t}")

    user_content = "\n\n".join(user_content_parts)

    service_client = tinker.ServiceClient()

    # Training checkpoints use /weights/ paths; sampling requires /sampler_weights/.
    # Materialize sampler weights once and reuse them on subsequent calls.
    if "/sampler_weights/" not in checkpoint_path:
        # Derive a deterministic sampler name from the checkpoint path so we
        # can reuse previously-materialized weights instead of re-creating them.
        checkpoint_basename = checkpoint_path.rsplit("/", 1)[-1]
        sampler_name = f"sampler__{checkpoint_basename}"
        sampler_name = sampler_name.replace("/", "_").replace(":", "-")
        sampler_name = "".join(
            ch for ch in sampler_name if ch.isalnum() or ch in {"_", "-", "."}
        )

        run_prefix = checkpoint_path.split("/weights/")[0]
        expected_sampler_path = f"{run_prefix}/sampler_weights/{sampler_name}"

        try:
            sampling_client = await service_client.create_sampling_client_async(
                base_model="meta-llama/Llama-3.1-8B-Instruct",
                model_path=expected_sampler_path,
            )
            logger.info("Reusing existing sampler weights at %s", expected_sampler_path)
        except Exception:
            logger.info("Materializing sampler weights for %s", checkpoint_path)
            tc = await service_client.create_training_client_from_state_async(
                checkpoint_path
            )
            sampling_client = await tc.save_weights_and_get_sampling_client_async(
                name=sampler_name
            )
            logger.info("Sampler weights materialized as %s", sampler_name)
    else:
        sampling_client = await service_client.create_sampling_client_async(
            base_model="meta-llama/Llama-3.1-8B-Instruct",
            model_path=checkpoint_path,
        )

    tokenizer = sampling_client.get_tokenizer()

    # Build chat messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Try to use the chat template for tokenization
    prompt_tokens: list[int] | None = None
    try:
        prompt_tokens = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True
        )
    except Exception:
        pass

    if prompt_tokens is None:
        # Fallback: plain-text prompt
        prompt_text = f"System:\n{SYSTEM_PROMPT}\n\nUser:\n{user_content}\n"
        prompt_tokens = tokenizer.encode(prompt_text)

    # tokenizer.encode() may return a BatchEncoding instead of list[int]
    if hasattr(prompt_tokens, "input_ids"):
        prompt_tokens = prompt_tokens.input_ids

    prompt = tinker.types.ModelInput.from_ints(prompt_tokens)
    params = tinker.types.SamplingParams(max_tokens=512, temperature=0.7)

    resp = await sampling_client.sample_async(prompt, 1, params)
    if not resp.sequences:
        raise RuntimeError("No sequences returned from sampling")

    completion_tokens = resp.sequences[0].tokens
    review_text = tokenizer.decode(completion_tokens, skip_special_tokens=True)

    return review_text.strip()
