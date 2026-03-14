"""
Application-level models for the orchestrator pipeline.

DB-row models are auto-generated in _generated.py (from Prisma schema).
This file re-exports those and adds custom models for pipeline-specific
data that doesn't map 1:1 to a DB table.

Regenerate DB models with:  uv run python scripts/generate_models.py
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ── Re-export all generated DB models ─────────────────────────
# Downstream code can keep importing from models.schemas as before.

from models._generated import (  # noqa: F401
    Account,
    Channel,
    ClassNode,
    ClassNodeResult,
    ClassNodeResultValue,
    Funnel,
    FunnelCreator,
    FunnelKeyword,
    GoldStandard,
    Review,
    Session,
    TrainingMethod,
    TrainingRun,
    TrainingStatus,
    User,
    VerificationToken,
    Video,
)


# ── Enriched models (with eagerly-loaded relations) ───────────


class GoldStandardWithContext(GoldStandard):
    """Gold standard enriched with review content and video summary for prompts."""

    review_content: str | None = Field(default=None)
    video_summary: str | None = Field(default=None)
    video_description: str | None = Field(default=None)


class ClassNodeWithRelations(ClassNode):
    """ClassNode with its children and gold standards loaded."""

    children: list[ClassNode] = Field(default_factory=list)
    gold_standards: list[GoldStandardWithContext] = Field(default_factory=list)


class FunnelWithRelations(Funnel):
    """Funnel with its keywords, creators, and full ClassNode tree."""

    keywords: list[FunnelKeyword] = Field(default_factory=list)
    creators: list[FunnelCreator] = Field(default_factory=list)
    # Flat list of all ClassNodes in this funnel (BFS order, root nodes first)
    class_nodes: list[ClassNodeWithRelations] = Field(default_factory=list)


# ── Pipeline-specific models ─────────────────────────────────


class VideoData(BaseModel):
    """Data extracted from YouTube via yt-dlp, ready to be saved to DB."""

    video_id: str
    title: str
    description: str = ""
    channel_title: str = ""
    channel_id: str = ""
    published_at: datetime | None = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_seconds: int = 0
    tags: list[str] = Field(default_factory=list)
    transcript: str | None = None
    transcript_status: str | None = None
    summary: str | None = None


class ClassNodeResultCreate(BaseModel):
    """Data to insert into the ClassNodeResult table."""

    video_id: str
    class_node_id: str
    result: ClassNodeResultValue
    explanation: str | None = None
    model_used: str | None = None
