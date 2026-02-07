"""
Training API routes.

POST /training/start       -- Start a training run (called by Application)
GET  /training/{id}        -- Get training run status
POST /training/{id}/cancel -- Cancel a running training
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from server.config import DEFAULT_BASE_MODEL, MIN_REVIEWS_FOR_TRAINING
from server.db import (
    create_training_run,
    get_next_version,
    get_training_data,
    get_training_run,
    user_and_topic_exist,
)
from server.models import (
    TrainingMethod,
    TrainingRunResponse,
    TrainingStartRequest,
    TrainingStartResponse,
    TrainingStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/start", response_model=TrainingStartResponse)
async def start_training(
    request: TrainingStartRequest,
) -> TrainingStartResponse:
    """
    Start a new training run for a user's topic.
    Called by the Application when a user triggers training from the UI.
    """
    logger.info(
        "Training request received: user_id=%s topic_id=%s method=%s",
        request.user_id,
        request.topic_id,
        request.method.value,
    )

    # Validate user + topic exist
    if not user_and_topic_exist(request.user_id, request.topic_id):
        logger.warning(
            "Topic not found: topic_id=%s user_id=%s",
            request.topic_id,
            request.user_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Topic {request.topic_id} not found for user {request.user_id}",
        )

    # Check minimum reviews
    datapoints = get_training_data(request.user_id, request.topic_id)
    logger.info(
        "Training data lookup: user_id=%s topic_id=%s found=%d datapoints",
        request.user_id,
        request.topic_id,
        len(datapoints),
    )
    if len(datapoints) < MIN_REVIEWS_FOR_TRAINING:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough reviews for training. "
                f"Found {len(datapoints)}, need at least {MIN_REVIEWS_FOR_TRAINING}. "
                f"Reviews must have feedback text and their videos must have transcripts."
            ),
        )

    # Compute model name and version
    version = get_next_version(request.user_id, request.topic_id, request.method)
    model_name = f"innie-{request.topic_id}-{request.method.value.lower()}-v{version}"

    # Build config dict from overrides
    config_dict: dict | None = None
    if request.config:
        config_dict = request.config.model_dump(exclude_none=True)

    # Create training run in DB
    run_id = create_training_run(
        user_id=request.user_id,
        topic_id=request.topic_id,
        method=request.method,
        model_name=model_name,
        version=version,
        base_model=DEFAULT_BASE_MODEL,
        config=config_dict,
        webhook_url=request.webhook_url,
        dataset_size=len(datapoints),
    )

    # Spawn background training task (tracked for cancellation)
    from server.training_task import start_training_task

    start_training_task(
        run_id=run_id,
        user_id=request.user_id,
        topic_id=request.topic_id,
        method=request.method,
        model_name=model_name,
        base_model=DEFAULT_BASE_MODEL,
        datapoints=datapoints,
        config_overrides=config_dict,
        webhook_url=request.webhook_url,
    )

    logger.info(
        "Training started run_id=%s model_name=%s method=%s dataset_size=%d",
        run_id,
        model_name,
        request.method.value,
        len(datapoints),
    )

    return TrainingStartResponse(
        trainingRunId=run_id,
        modelName=model_name,
        status=TrainingStatus.PENDING,
    )


@router.get("/{training_run_id}", response_model=TrainingRunResponse)
async def get_training_status(training_run_id: str) -> TrainingRunResponse:
    """Get the current status of a training run."""
    run = get_training_run(training_run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Training run {training_run_id} not found",
        )
    return run


@router.post("/{training_run_id}/cancel")
async def cancel_training(training_run_id: str) -> dict:
    """Cancel a running training task."""
    run = get_training_run(training_run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Training run {training_run_id} not found",
        )

    if run.status not in (TrainingStatus.PENDING, TrainingStatus.TRAINING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel training run with status {run.status.value}",
        )

    from server.training_task import cancel_training_task

    cancelled = cancel_training_task(training_run_id)
    if not cancelled:
        # Task might not be in memory (e.g. server restarted), but we can
        # still update the DB status
        from server.db import update_training_run_status

        update_training_run_status(training_run_id, TrainingStatus.CANCELLED)

    return {"status": "cancelled", "trainingRunId": training_run_id}
