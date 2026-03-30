"""
Application-level models for the orchestrator pipeline.

DB-row models are auto-generated in _generated.py (from Prisma schema).
This file re-exports those and adds custom models for pipeline-specific
data that doesn't map 1:1 to a DB table.

Regenerate DB models with:  uv run python scripts/generate_models.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Re-export all generated DB models ─────────────────────────
# Downstream code can keep importing from models.schemas as before.

from models._generated import (  # noqa: F401
    Account,
    Channel,
    ClassNode,
    ClassNodeModelVerdict,
    ClassNodeResult,
    ClassNodeResultValue,
    Funnel,
    FunnelCreator,
    FunnelKeyword,
    GoldStandard,
    IdeaGraph,
    IdeaGraphEdge,
    IdeaGraphEdgeType,
    IdeaGraphGenerationStatus,
    IdeaGraphNode,
    IdeaGraphNodeSource,
    IdeaGraphNodeType,
    LLM,
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
    confidence_score: float
    explanation: str | None = None


class ClassNodeModelVerdictCreate(BaseModel):
    """Data to insert into the ClassNodeModelVerdict table."""

    video_id: str
    class_node_id: str
    class_node_result_id: str
    llm_id: str
    rationale: str
    verdict: bool


class IdeaGraphSourcePayload(BaseModel):
    id: str
    paraphrase: str | None = None
    quote: str
    start_sec: float
    end_sec: float


class IdeaGraphNodePayload(BaseModel):
    id: str
    type: IdeaGraphNodeType
    title: str = ""
    content: str | None = None
    x: float = 0
    y: float = 0
    collapsed: bool = False
    transcript_sources: list[IdeaGraphSourcePayload] = Field(default_factory=list)


class IdeaGraphEdgePayload(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    type: IdeaGraphEdgeType
    label: str | None = None


class IdeaGraphSnapshot(BaseModel):
    nodes: list[IdeaGraphNodePayload] = Field(default_factory=list)
    edges: list[IdeaGraphEdgePayload] = Field(default_factory=list)


class TranscriptSegment(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class IdeaGraphGenerationInput(BaseModel):
    user_id: str
    video_id: str
    video_title: str
    transcript: str
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    current_graph: IdeaGraphSnapshot = Field(default_factory=IdeaGraphSnapshot)


IdeaGraphAgentEventType = Literal[
    "chunk_index_ready",
    "chunk_read",
    "node_added",
    "node_updated",
    "edge_added",
    "source_attached",
    "snapshot",
    "task_completed",
]

IdeaGraphStreamEventType = Literal[
    "generation_started",
    "chunk_index_ready",
    "chunk_read",
    "node_added",
    "node_updated",
    "edge_added",
    "source_attached",
    "snapshot",
    "completed",
    "failed",
]


class IdeaGraphAgentCustomEvent(BaseModel):
    event_type: IdeaGraphAgentEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class IdeaGraphStreamEvent(BaseModel):
    generation_id: str
    event_id: int
    user_id: str
    video_id: str
    timestamp: datetime
    type: IdeaGraphStreamEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class IdeaGraphGenerationMetadata(BaseModel):
    generation_id: str
    graph_id: str
    user_id: str
    video_id: str
    status: IdeaGraphGenerationStatus
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    last_event_id: int = 0
    thread_id: str | None = None
    run_id: str | None = None


class IdeaGraphGenerationStartResponse(BaseModel):
    generation_id: str
    graph_id: str
    user_id: str
    video_id: str
    status: IdeaGraphGenerationStatus


class ActiveIdeaGraphGenerationResponse(BaseModel):
    active: bool
    generation: IdeaGraphGenerationMetadata | None = None
