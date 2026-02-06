"""
Background training task.

Adapts DB-sourced training data into the format expected by the existing
training scripts, runs training, updates DB status, and sends webhooks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from server.db import mark_active_model, update_training_run_status
from server.models import (
    TrainingDatapoint,
    TrainingMethod,
    TrainingStatus,
    TrainingWebhookPayload,
)

logger = logging.getLogger(__name__)

# ── Task tracking for cancellation ────────────────────────────

_running_tasks: dict[str, asyncio.Task] = {}


def start_training_task(
    run_id: str,
    **kwargs: Any,
) -> asyncio.Task:
    """Create and track an asyncio task for a training run."""
    task = asyncio.create_task(run_training_background(run_id=run_id, **kwargs))
    _running_tasks[run_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        _running_tasks.pop(run_id, None)

    task.add_done_callback(_cleanup)
    return task


def cancel_training_task(run_id: str) -> bool:
    """
    Cancel a running training task. Returns True if cancelled, False if not found.
    """
    task = _running_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        update_training_run_status(run_id, TrainingStatus.CANCELLED)
        logger.info("Cancelled training task run_id=%s", run_id)
        return True
    return False


def is_training_running(run_id: str) -> bool:
    """Check if a training task is currently running."""
    task = _running_tasks.get(run_id)
    return task is not None and not task.done()


def _datapoints_to_sft_format(
    datapoints: list[TrainingDatapoint],
) -> list[dict[str, Any]]:
    """
    Convert DB-sourced TrainingDatapoints into the dict format that
    the SFT training script expects (mimicking YouTubeReviewDatapoint).
    """
    from trains.rlvr_youtube_reviews.dataset import YouTubeReviewDatapoint

    results: list[YouTubeReviewDatapoint] = []
    for dp in datapoints:
        results.append(
            YouTubeReviewDatapoint(
                example_id=f"{dp.video_id}::{dp.topic_name}",
                video_id=dp.video_id,
                video_url=f"https://www.youtube.com/watch?v={dp.video_id}",
                title=dp.video_title,
                # Use topic info in place of persona
                persona_id=dp.topic_name,
                persona_title=dp.topic_name,
                persona_description=dp.topic_description,
                summary="",  # We don't have pre-generated summaries from DB
                transcript=dp.transcript,
                # The user's actual feedback becomes the training target
                synthetic_user_feedback=dp.feedback,
                feedback_embedding=None,
                feedback_embedding_ref=None,
            )
        )
    return results


async def _run_sft(
    datapoints: list[TrainingDatapoint],
    model_name: str,
    base_model: str,
    config_overrides: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """
    Run SFT training and return (checkpoint_path, metrics).
    """
    from trains.sft_youtube_reviews.train import Config as SFTConfig, train as sft_train

    adapted = _datapoints_to_sft_format(datapoints)

    # Build config with overrides
    overrides: dict[str, Any] = {}
    if config_overrides:
        if "learning_rate" in config_overrides:
            overrides["learning_rate"] = config_overrides["learning_rate"]
        if "epochs" in config_overrides:
            overrides["epochs"] = config_overrides["epochs"]
        if "batch_size" in config_overrides:
            overrides["batch_size"] = config_overrides["batch_size"]
        if "lora_rank" in config_overrides:
            overrides["lora_rank"] = config_overrides["lora_rank"]

    cfg = SFTConfig(
        base_model=base_model,
        checkpoint_every_steps=0,  # No intermediate checkpoints
        checkpoint_name_prefix=model_name,
        **overrides,
    )

    result = await sft_train(cfg, datapoints_override=adapted)

    return result.checkpoint_path, result.metrics


async def _run_rlvr(
    datapoints: list[TrainingDatapoint],
    model_name: str,
    base_model: str,
    config_overrides: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """
    Run RLVR training and return (checkpoint_path, metrics).
    """
    from trains.rlvr_youtube_reviews.train import (
        Config as RLVRConfig,
        train as rlvr_train,
    )

    adapted = _datapoints_to_sft_format(datapoints)

    # Build config with overrides
    overrides: dict[str, Any] = {}
    if config_overrides:
        if "learning_rate" in config_overrides:
            overrides["learning_rate"] = config_overrides["learning_rate"]
        if "lora_rank" in config_overrides:
            overrides["lora_rank"] = config_overrides["lora_rank"]
        if "steps" in config_overrides:
            overrides["steps"] = config_overrides["steps"]
        if "groups_per_batch" in config_overrides:
            overrides["groups_per_batch"] = config_overrides["groups_per_batch"]
        if "group_size" in config_overrides:
            overrides["group_size"] = config_overrides["group_size"]
        if "max_tokens" in config_overrides:
            overrides["max_tokens"] = config_overrides["max_tokens"]

    cfg = RLVRConfig(
        base_model=base_model,
        checkpoint_every_steps=0,  # No intermediate checkpoints
        checkpoint_name_prefix=model_name,
        persona_id=None,  # Don't filter by persona
        **overrides,
    )

    result = await rlvr_train(cfg, datapoints_override=adapted)

    return result.checkpoint_path, result.metrics


async def run_training_background(
    *,
    run_id: str,
    user_id: str,
    topic_id: str,
    method: TrainingMethod,
    model_name: str,
    base_model: str,
    datapoints: list[TrainingDatapoint],
    config_overrides: dict[str, Any] | None,
    webhook_url: str | None,
) -> None:
    """
    Background task that runs a full training cycle:
    1. Update status to TRAINING
    2. Run the appropriate training method
    3. Update DB with results
    4. Mark as active model
    5. Send webhook notification
    """
    logger.info(
        "Background training starting run_id=%s model=%s method=%s",
        run_id,
        model_name,
        method.value,
    )

    # Update status to TRAINING
    update_training_run_status(run_id, TrainingStatus.TRAINING)

    try:
        if method == TrainingMethod.SFT:
            checkpoint_path, metrics = await _run_sft(
                datapoints=datapoints,
                model_name=model_name,
                base_model=base_model,
                config_overrides=config_overrides,
            )
        elif method == TrainingMethod.RLVR:
            checkpoint_path, metrics = await _run_rlvr(
                datapoints=datapoints,
                model_name=model_name,
                base_model=base_model,
                config_overrides=config_overrides,
            )
        else:
            raise ValueError(f"Unknown training method: {method}")

        # Update DB with success
        update_training_run_status(
            run_id,
            TrainingStatus.COMPLETED,
            checkpoint_path=checkpoint_path,
            metrics=metrics,
        )

        # Mark as active model (deactivate previous)
        mark_active_model(run_id, topic_id, method)

        logger.info(
            "Training completed run_id=%s checkpoint=%s",
            run_id,
            checkpoint_path,
        )

        # Send webhook
        if webhook_url:
            await _send_webhook(
                webhook_url=webhook_url,
                payload=TrainingWebhookPayload(
                    event="training.completed",
                    trainingRunId=run_id,
                    modelName=model_name,
                    status=TrainingStatus.COMPLETED,
                    userId=user_id,
                    topicId=topic_id,
                    method=method,
                    metrics=metrics,
                    completedAt=datetime.now(timezone.utc),
                ),
            )

    except asyncio.CancelledError:
        logger.info("Training cancelled run_id=%s", run_id)
        # Status already set to CANCELLED by cancel_training_task()
        if webhook_url:
            await _send_webhook(
                webhook_url=webhook_url,
                payload=TrainingWebhookPayload(
                    event="training.cancelled",
                    trainingRunId=run_id,
                    modelName=model_name,
                    status=TrainingStatus.CANCELLED,
                    userId=user_id,
                    topicId=topic_id,
                    method=method,
                ),
            )

    except Exception as e:
        error_msg = str(e)
        logger.exception("Training failed run_id=%s error=%s", run_id, error_msg)

        update_training_run_status(
            run_id,
            TrainingStatus.FAILED,
            error=error_msg,
        )

        # Send failure webhook
        if webhook_url:
            await _send_webhook(
                webhook_url=webhook_url,
                payload=TrainingWebhookPayload(
                    event="training.failed",
                    trainingRunId=run_id,
                    modelName=model_name,
                    status=TrainingStatus.FAILED,
                    userId=user_id,
                    topicId=topic_id,
                    method=method,
                    error=error_msg,
                ),
            )


async def _send_webhook(webhook_url: str, payload: TrainingWebhookPayload) -> None:
    """Send a webhook notification. Best-effort, logs errors but doesn't raise."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                webhook_url,
                json=payload.model_dump(by_alias=True),
            )
            logger.info(
                "Webhook sent url=%s status=%d event=%s",
                webhook_url,
                resp.status_code,
                payload.event,
            )
    except Exception:
        logger.exception("Failed to send webhook to %s", webhook_url)
