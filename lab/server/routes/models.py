"""
Models listing API route.

GET /models -- List available trained models.
Called by both Application and Orchestrator.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from server.db import list_models
from server.models import ModelsListResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsListResponse)
async def get_models(
    user_id: str | None = Query(None, alias="userId"),
    topic_id: str | None = Query(None, alias="topicId"),
) -> ModelsListResponse:
    """List completed training runs, optionally filtered by user and/or topic."""
    models = list_models(user_id=user_id, topic_id=topic_id)
    return ModelsListResponse(models=models)
