"""
Pydantic request/response schemas for the lab FastAPI server.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────


class TrainingMethod(str, Enum):
    SFT = "SFT"
    RLVR = "RLVR"


class TrainingStatus(str, Enum):
    PENDING = "PENDING"
    TRAINING = "TRAINING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ── Training request/response ────────────────────────────────


class TrainingConfig(BaseModel):
    """Optional overrides for training hyperparameters."""

    learning_rate: float | None = None
    epochs: int | None = None
    batch_size: int | None = None
    lora_rank: int | None = None
    max_tokens: int | None = None
    steps: int | None = None  # RLVR only
    groups_per_batch: int | None = None  # RLVR only
    group_size: int | None = None  # RLVR only


class TrainingStartRequest(BaseModel):
    user_id: str = Field(..., alias="userId")
    topic_id: str = Field(..., alias="topicId")
    method: TrainingMethod
    webhook_url: str | None = Field(None, alias="webhookUrl")
    config: TrainingConfig | None = None

    model_config = {"populate_by_name": True}


class TrainingStartResponse(BaseModel):
    training_run_id: str = Field(..., alias="trainingRunId")
    model_name: str = Field(..., alias="modelName")
    status: TrainingStatus

    model_config = {"populate_by_name": True}


class TrainingRunResponse(BaseModel):
    id: str
    user_id: str = Field(..., alias="userId")
    topic_id: str = Field(..., alias="topicId")
    status: TrainingStatus
    method: TrainingMethod
    model_name: str = Field(..., alias="modelName")
    version: int
    checkpoint_path: str | None = Field(None, alias="checkpointPath")
    base_model: str = Field(..., alias="baseModel")
    config: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    dataset_size: int | None = Field(None, alias="datasetSize")
    error: str | None = None
    is_active: bool = Field(False, alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    completed_at: datetime | None = Field(None, alias="completedAt")

    model_config = {"populate_by_name": True}


# ── Inference request/response ───────────────────────────────


class InferenceRequest(BaseModel):
    """
    Inference can be requested either by model_name (explicit) or by
    topic_id + method (looks up the active model).
    """

    model_name: str | None = Field(None, alias="modelName")
    topic_id: str | None = Field(None, alias="topicId")
    method: TrainingMethod | None = None
    transcript: str
    video_title: str | None = Field(None, alias="videoTitle")

    model_config = {"populate_by_name": True}


class InferenceResponse(BaseModel):
    review: str
    model_name: str = Field(..., alias="modelName")

    model_config = {"populate_by_name": True}


# ── Models list response ─────────────────────────────────────


class ModelsListResponse(BaseModel):
    models: list[TrainingRunResponse]


# ── Webhook payload ──────────────────────────────────────────


class TrainingWebhookPayload(BaseModel):
    event: str  # "training.completed" or "training.failed"
    training_run_id: str = Field(..., alias="trainingRunId")
    model_name: str = Field(..., alias="modelName")
    status: TrainingStatus
    user_id: str = Field(..., alias="userId")
    topic_id: str = Field(..., alias="topicId")
    method: TrainingMethod
    metrics: dict[str, Any] | None = None
    error: str | None = None
    completed_at: datetime | None = Field(None, alias="completedAt")

    model_config = {"populate_by_name": True}


# ── Internal datapoints ─────────────────────────────────────


class TrainingDatapoint(BaseModel):
    """A single training example built from DB data."""

    video_id: str
    video_title: str
    transcript: str
    rating: int  # 1=dislike, 3=neutral, 5=like
    feedback: str  # user's free-text feedback
    like_aspects: list[str]  # e.g. ["topic", "style", "quality"]
    topic_name: str
    topic_description: str
