from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


NODE_TYPES = (
    "CLAIM",
    "EVIDENCE",
    "COUNTERARGUMENT",
    "REBUTTAL",
    "EXAMPLE",
    "ASSUMPTION",
    "DEFINITION",
    "QUESTION",
    "CONCLUSION",
)

EDGE_TYPES = (
    "SUPPORTS",
    "ATTACKS",
    "REBUTS",
    "ELABORATES",
    "DEPENDS_ON",
    "ILLUSTRATES",
    "CONTRASTS_WITH",
)

SYSTEM_PROMPT_TEMPLATE = """
You are building a video idea graph for understanding content.

Read transcript chunks progressively instead of assuming the whole transcript at once. The chunk list already covers the whole transcript in a reduced number of larger chunks.

Allowed node types: {node_types}.
Allowed edge types: {edge_types}.

Build a coherent multi-claim graph, not just a tree. Prefer claims and conclusions for high-level ideas, evidence and examples for support, and counterarguments or rebuttals when the speaker presents tension or opposition.

Attach transcript sources with quote plus start/end timestamps whenever possible.

Create enough structure to capture the main ideas of the whole video, including cross-links when useful.

Do not invent citations that are not grounded in transcript chunks you have read.
""".strip()

USER_PROMPT_TEMPLATE = """
Video title: {video_title}
Video id: {video_id}

Start by listing transcript chunks and reading all of them once before building the graph.

Then build the complete graph using the tools.

If current graph state already has nodes, inspect it first and replace it logically with a better complete graph.
""".strip()


class TranscriptSegment(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class TranscriptChunk(BaseModel):
    index: int
    text: str
    start_sec: float
    end_sec: float


class IdeaGraphSource(BaseModel):
    id: str
    paraphrase: str | None = None
    quote: str
    start_sec: float
    end_sec: float


class IdeaGraphNode(BaseModel):
    id: str
    type: str
    title: str = ""
    content: str | None = None
    x: float = 0
    y: float = 0
    collapsed: bool = False
    transcript_sources: list[IdeaGraphSource] = Field(default_factory=list)


class IdeaGraphEdge(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    type: str
    label: str | None = None


class IdeaGraphSnapshot(BaseModel):
    nodes: list[IdeaGraphNode] = Field(default_factory=list)
    edges: list[IdeaGraphEdge] = Field(default_factory=list)


class BuildIdeaGraphState(BaseModel):
    user_id: str
    video_id: str
    video_title: str
    transcript: str
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    current_graph: IdeaGraphSnapshot = Field(default_factory=IdeaGraphSnapshot)
    result_graph: IdeaGraphSnapshot = Field(default_factory=IdeaGraphSnapshot)


def _serialize_source(source: IdeaGraphSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "paraphrase": source.paraphrase,
        "quote": source.quote,
        "startSec": source.start_sec,
        "endSec": source.end_sec,
    }


def _serialize_node(node: IdeaGraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.type,
        "title": node.title,
        "content": node.content,
        "x": node.x,
        "y": node.y,
        "collapsed": node.collapsed,
        "transcriptSources": [_serialize_source(source) for source in node.transcript_sources],
    }


def _serialize_edge(edge: IdeaGraphEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "sourceNodeId": edge.source_node_id,
        "targetNodeId": edge.target_node_id,
        "type": edge.type,
        "label": edge.label,
    }


def _serialize_snapshot(snapshot: IdeaGraphSnapshot) -> dict[str, Any]:
    return {
        "nodes": [_serialize_node(node) for node in snapshot.nodes],
        "edges": [_serialize_edge(edge) for edge in snapshot.edges],
    }


def _chunk_transcript(
    transcript: str,
    transcript_segments: list[TranscriptSegment],
    max_chars: int = 12000,
    fallback_overlap: int = 300,
    max_chunks: int = 8,
) -> list[TranscriptChunk]:
    if transcript_segments:
        chunks: list[TranscriptChunk] = []
        current: list[TranscriptSegment] = []
        current_chars = 0

        for segment in transcript_segments:
            segment_len = len(segment.text) + 1
            if current and current_chars + segment_len > max_chars:
                chunks.append(
                    TranscriptChunk(
                        index=len(chunks),
                        text=" ".join(item.text for item in current),
                        start_sec=current[0].start_sec,
                        end_sec=current[-1].end_sec,
                    )
                )
                current = []
                current_chars = 0
            current.append(segment)
            current_chars += segment_len

        if current:
            chunks.append(
                TranscriptChunk(
                    index=len(chunks),
                    text=" ".join(item.text for item in current),
                    start_sec=current[0].start_sec,
                    end_sec=current[-1].end_sec,
                )
            )
        if len(chunks) <= max_chunks:
            return chunks

        merged_chunks: list[TranscriptChunk] = []
        group_size = max(1, (len(chunks) + max_chunks - 1) // max_chunks)
        for start_idx in range(0, len(chunks), group_size):
            group = chunks[start_idx:start_idx + group_size]
            merged_chunks.append(
                TranscriptChunk(
                    index=len(merged_chunks),
                    text=" ".join(chunk.text for chunk in group),
                    start_sec=group[0].start_sec,
                    end_sec=group[-1].end_sec,
                )
            )
        return merged_chunks

    normalized = transcript.strip()
    if not normalized:
        return []

    chunks: list[TranscriptChunk] = []
    start = 0
    chunk_size = max_chars
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        text = normalized[start:end].strip()
        if text:
            chunks.append(
                TranscriptChunk(
                    index=len(chunks),
                    text=text,
                    start_sec=0,
                    end_sec=0,
                )
            )
        if end >= len(normalized):
            break
        start = max(0, end - fallback_overlap)
    if len(chunks) <= max_chunks:
        return chunks

    merged_chunks: list[TranscriptChunk] = []
    group_size = max(1, (len(chunks) + max_chunks - 1) // max_chunks)
    for start_idx in range(0, len(chunks), group_size):
        group = chunks[start_idx:start_idx + group_size]
        merged_chunks.append(
            TranscriptChunk(
                index=len(merged_chunks),
                text="\n\n".join(chunk.text for chunk in group),
                start_sec=group[0].start_sec,
                end_sec=group[-1].end_sec,
            )
        )
    return merged_chunks


class IdeaGraphContext:
    def __init__(self, state: BuildIdeaGraphState, writer):
        self.graph = IdeaGraphSnapshot.model_validate(deepcopy(state.current_graph.model_dump()))
        self.chunks = _chunk_transcript(state.transcript, state.transcript_segments)
        self.writer = writer
        self.mutation_count = 0

    def _node_ids(self) -> set[str]:
        return {node.id for node in self.graph.nodes}

    def _edge_ids(self) -> set[str]:
        return {edge.id for edge in self.graph.edges}

    def _make_id(self, prefix: str, existing: set[str]) -> str:
        while True:
            candidate = f"{prefix}_{uuid4().hex[:10]}"
            if candidate not in existing:
                return candidate

    def snapshot_json(self) -> str:
        return json.dumps(self.graph.model_dump(mode="json"), ensure_ascii=True)

    def snapshot_payload(self) -> dict[str, Any]:
        return _serialize_snapshot(self.graph)

    def chunk_index_json(self) -> str:
        payload = [
            {
                "index": chunk.index,
                "start_sec": chunk.start_sec,
                "end_sec": chunk.end_sec,
                "preview": chunk.text[:180],
            }
            for chunk in self.chunks
        ]
        return json.dumps(payload, ensure_ascii=True)

    def chunk_index_payload(self) -> dict[str, Any]:
        return {
            "chunks": [
                {
                    "index": chunk.index,
                    "startSec": chunk.start_sec,
                    "endSec": chunk.end_sec,
                    "preview": chunk.text[:180],
                }
                for chunk in self.chunks
            ],
            "count": len(self.chunks),
        }

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.writer is None:
            return
        self.writer({"event_type": event_type, "payload": payload})

    def _emit_snapshot_if_needed(self, *, force: bool = False) -> None:
        if force or self.mutation_count % 5 == 0:
            self._emit("snapshot", {"graph": self.snapshot_payload()})

    def read_chunk(self, index: int) -> str:
        if index < 0 or index >= len(self.chunks):
            raise ValueError(f"Chunk index {index} is out of range")
        chunk = self.chunks[index]
        self._emit(
            "chunk_read",
            {
                "index": chunk.index,
                "startSec": chunk.start_sec,
                "endSec": chunk.end_sec,
                "preview": chunk.text[:180],
            },
        )
        return json.dumps(chunk.model_dump(mode="json"), ensure_ascii=True)

    def add_node(self, node_type: str, title: str, content: str | None = None) -> str:
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unsupported node type: {node_type}")
        node_id = self._make_id("node", self._node_ids())
        node = IdeaGraphNode(
            id=node_id,
            type=node_type,
            title=title.strip(),
            content=content.strip() if content else None,
        )
        self.graph.nodes.append(node)
        self.mutation_count += 1
        self._emit("node_added", {"node": _serialize_node(node)})
        self._emit_snapshot_if_needed()
        return node_id

    def update_node(
        self,
        node_id: str,
        title: str | None = None,
        content: str | None = None,
        node_type: str | None = None,
        collapsed: bool | None = None,
    ) -> str:
        for node in self.graph.nodes:
            if node.id != node_id:
                continue
            if node_type is not None:
                if node_type not in NODE_TYPES:
                    raise ValueError(f"Unsupported node type: {node_type}")
                node.type = node_type
            if title is not None:
                node.title = title.strip()
            if content is not None:
                node.content = content.strip() if content else None
            if collapsed is not None:
                node.collapsed = collapsed
            self.mutation_count += 1
            self._emit("node_updated", {"node": _serialize_node(node)})
            self._emit_snapshot_if_needed()
            return node_id
        raise ValueError(f"Unknown node id: {node_id}")

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str | None = None,
    ) -> str:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unsupported edge type: {edge_type}")
        node_ids = self._node_ids()
        if source_node_id not in node_ids or target_node_id not in node_ids:
            raise ValueError("Both source and target nodes must already exist")

        edge_id = self._make_id("edge", self._edge_ids())
        edge = IdeaGraphEdge(
            id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            type=edge_type,
            label=label.strip() if label else None,
        )
        self.graph.edges.append(edge)
        self.mutation_count += 1
        self._emit("edge_added", {"edge": _serialize_edge(edge)})
        self._emit_snapshot_if_needed()
        return edge_id

    def attach_source(
        self,
        node_id: str,
        quote: str,
        start_sec: float,
        end_sec: float,
        paraphrase: str | None = None,
    ) -> str:
        for node in self.graph.nodes:
            if node.id != node_id:
                continue
            source_id = self._make_id(
                "source",
                {source.id for candidate in self.graph.nodes for source in candidate.transcript_sources},
            )
            source = IdeaGraphSource(
                id=source_id,
                paraphrase=paraphrase.strip() if paraphrase else None,
                quote=quote.strip(),
                start_sec=start_sec,
                end_sec=end_sec,
            )
            node.transcript_sources.append(source)
            self.mutation_count += 1
            self._emit(
                "source_attached",
                {
                    "nodeId": node_id,
                    "source": _serialize_source(source),
                },
            )
            self._emit_snapshot_if_needed()
            return source_id
        raise ValueError(f"Unknown node id: {node_id}")


async def generate_idea_graph(state: BuildIdeaGraphState):
    writer = get_stream_writer()
    ctx = IdeaGraphContext(state, writer)
    ctx._emit("chunk_index_ready", ctx.chunk_index_payload())

    @tool
    def read_graph_state() -> str:
        """Read the current graph state as JSON."""
        return ctx.snapshot_json()

    @tool
    def list_transcript_chunks() -> str:
        """List available transcript chunks with indexes and time ranges."""
        return ctx.chunk_index_json()

    @tool
    def read_transcript_chunk(index: int) -> str:
        """Read one transcript chunk by index."""
        return ctx.read_chunk(index)

    @tool
    def add_node(
        node_type: Literal[
            "CLAIM",
            "EVIDENCE",
            "COUNTERARGUMENT",
            "REBUTTAL",
            "EXAMPLE",
            "ASSUMPTION",
            "DEFINITION",
            "QUESTION",
            "CONCLUSION",
        ],
        title: str,
        content: str | None = None,
    ) -> str:
        """Create a graph node and return its id."""
        return ctx.add_node(node_type=node_type, title=title, content=content)

    @tool
    def update_node(
        node_id: str,
        title: str | None = None,
        content: str | None = None,
        node_type: Literal[
            "CLAIM",
            "EVIDENCE",
            "COUNTERARGUMENT",
            "REBUTTAL",
            "EXAMPLE",
            "ASSUMPTION",
            "DEFINITION",
            "QUESTION",
            "CONCLUSION",
        ]
        | None = None,
        collapsed: bool | None = None,
    ) -> str:
        """Update an existing node."""
        return ctx.update_node(
            node_id=node_id,
            title=title,
            content=content,
            node_type=node_type,
            collapsed=collapsed,
        )

    @tool
    def add_edge(
        source_node_id: str,
        target_node_id: str,
        edge_type: Literal[
            "SUPPORTS",
            "ATTACKS",
            "REBUTS",
            "ELABORATES",
            "DEPENDS_ON",
            "ILLUSTRATES",
            "CONTRASTS_WITH",
        ],
        label: str | None = None,
    ) -> str:
        """Create a typed graph edge and return its id."""
        return ctx.add_edge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            label=label,
        )

    @tool
    def attach_source(
        node_id: str,
        quote: str,
        start_sec: float,
        end_sec: float,
        paraphrase: str | None = None,
    ) -> str:
        """Attach a transcript-backed quote and time range to an existing node."""
        return ctx.attach_source(
            node_id=node_id,
            quote=quote,
            start_sec=start_sec,
            end_sec=end_sec,
            paraphrase=paraphrase,
        )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        node_types=", ".join(NODE_TYPES),
        edge_types=", ".join(EDGE_TYPES),
    )

    llm = ChatOpenAI(model="gpt-5.4-pro")
    agent = create_agent(
        model=llm,
        tools=[
            read_graph_state,
            list_transcript_chunks,
            read_transcript_chunk,
            add_node,
            update_node,
            add_edge,
            attach_source,
        ],
        system_prompt=system_prompt,
    )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        video_title=state.video_title,
        video_id=state.video_id,
    )

    await agent.ainvoke(
        {
            "messages": [
                HumanMessage(content=user_prompt),
            ]
        }
    )

    ctx._emit_snapshot_if_needed(force=True)
    return {"result_graph": ctx.graph}


graph = StateGraph(BuildIdeaGraphState)
graph.add_node(generate_idea_graph)
graph.add_edge(START, "generate_idea_graph")
graph.add_edge("generate_idea_graph", END)
g = graph.compile()
