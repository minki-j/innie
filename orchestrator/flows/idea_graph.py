from __future__ import annotations

import logging
import threading
import time
from typing import Any

from langgraph_sdk import get_sync_client

from config import LANGGRAPH_API_KEY, LANGGRAPH_API_URL
from models.schemas import (
    IdeaGraphAgentCustomEvent,
    IdeaGraphGenerationInput,
    IdeaGraphGenerationStatus,
    IdeaGraphSnapshot,
)
from tasks.db import (
    get_idea_graph_snapshot,
    get_video_for_idea_graph,
    replace_idea_graph,
    set_idea_graph_generation_status,
)
from tasks.youtube import fetch_transcript_segments
from utils.idea_graph_events import get_idea_graph_event_store
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def _serialize_snapshot(snapshot: IdeaGraphSnapshot) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": node.id,
                "type": node.type.value,
                "title": node.title,
                "content": node.content,
                "x": node.x,
                "y": node.y,
                "collapsed": node.collapsed,
                "transcriptSources": [
                    {
                        "id": source.id,
                        "paraphrase": source.paraphrase,
                        "quote": source.quote,
                        "startSec": source.start_sec,
                        "endSec": source.end_sec,
                    }
                    for source in node.transcript_sources
                ],
            }
            for node in snapshot.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "sourceNodeId": edge.source_node_id,
                "targetNodeId": edge.target_node_id,
                "type": edge.type.value,
                "label": edge.label,
            }
            for edge in snapshot.edges
        ],
    }


def generate_idea_graph_for_video(
    generation_id: str,
    user_id: str,
    video_id: str,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """
    Generate an idea graph for a specific user/video pair via LangGraph.

    The LangGraph agent reads transcript chunks and the current graph state, then
    returns a full replacement graph snapshot.
    """
    event_store = get_idea_graph_event_store()
    set_idea_graph_generation_status(
        user_id=user_id,
        video_id=video_id,
        status=IdeaGraphGenerationStatus.GENERATING,
        error=None,
    )

    try:
        video = get_video_for_idea_graph(video_id)
        if not video:
            raise ValueError(f"Video not found: {video_id}")
        if not video["transcript"]:
            raise ValueError(f"Video {video_id} does not have a transcript")

        transcript_segments, segment_status = fetch_transcript_segments(video_id)
        logger.info(
            "Idea graph transcript segments for %s: %s (%s)",
            video_id,
            "loaded" if transcript_segments else "missing",
            segment_status,
        )

        current_graph = get_idea_graph_snapshot(user_id=user_id, video_id=video_id)
        event_store.append_event(
            generation_id,
            event_type="generation_started",
            payload={
                "replace_existing": replace_existing,
                "video_title": video["title"],
                "initial_graph": _serialize_snapshot(current_graph),
            },
        )
        graph_input = IdeaGraphGenerationInput(
            user_id=user_id,
            video_id=video_id,
            video_title=video["title"],
            transcript=video["transcript"],
            transcript_segments=transcript_segments or [],
            current_graph=current_graph if replace_existing else IdeaGraphSnapshot(),
        )

        logger.info(
            "Calling build_idea_graph LangGraph agent for user=%s video=%s (url=%s)",
            user_id,
            video_id,
            LANGGRAPH_API_URL,
        )

        get_rate_limiter("langgraph").acquire()

        client = get_sync_client(
            url=LANGGRAPH_API_URL,
            api_key=LANGGRAPH_API_KEY or None,
        )
        thread = client.threads.create()
        event_store.set_run_metadata(generation_id, thread_id=thread["thread_id"])

        def _on_run_created(metadata: dict[str, Any]) -> None:
            run_id = metadata.get("run_id")
            if run_id:
                event_store.set_run_metadata(generation_id, run_id=run_id)

        stream_iterator = client.runs.stream(
            thread_id=thread["thread_id"],
            assistant_id="build_idea_graph",
            input=graph_input.model_dump(mode="json"),
            stream_mode=["custom"],
            stream_resumable=True,
            on_disconnect="continue",
            version="v2",
            on_run_created=_on_run_created,
        )
        stream_error: list[Exception] = []
        stop_stream = threading.Event()
        stream_thread: threading.Thread | None = None

        def _consume_stream() -> None:
            try:
                for part in stream_iterator:
                    if stop_stream.is_set():
                        break
                    part_type = part.get("type")
                    if part_type == "metadata":
                        run_id = part.get("data", {}).get("run_id")
                        if run_id:
                            event_store.set_run_metadata(generation_id, run_id=run_id)
                        continue
                    if part_type != "custom":
                        continue

                    custom_event = IdeaGraphAgentCustomEvent.model_validate(part.get("data") or {})
                    event_store.append_event(
                        generation_id,
                        event_type=custom_event.event_type,
                        payload=custom_event.payload,
                    )
            except Exception as exc:  # pragma: no cover - exercised in integration
                if not stop_stream.is_set():
                    stream_error.append(exc)

        try:
            stream_thread = threading.Thread(
                target=_consume_stream,
                name=f"idea-graph-stream-{generation_id}",
                daemon=True,
            )
            stream_thread.start()

            result_graph = None
            deadline = time.time() + 600
            while time.time() < deadline:
                if stream_error:
                    raise stream_error[0]
                state = client.threads.get_state(thread_id=thread["thread_id"])
                result_graph = state["values"].get("result_graph")
                if result_graph:
                    break
                time.sleep(1)
        finally:
            stop_stream.set()
            if stream_thread is not None:
                stream_thread.join(timeout=2)
                if stream_thread.is_alive():
                    logger.warning(
                        "Idea graph stream thread still draining after completion for generation=%s",
                        generation_id,
                    )

        if not result_graph:
            raise TimeoutError("LangGraph run did not produce result_graph before timeout")

        snapshot = IdeaGraphSnapshot.model_validate(result_graph)
        replace_idea_graph(user_id=user_id, video_id=video_id, snapshot=snapshot)
        set_idea_graph_generation_status(
            user_id=user_id,
            video_id=video_id,
            status=IdeaGraphGenerationStatus.COMPLETED,
            error=None,
        )
        event_store.mark_completed(
            generation_id,
            payload={
                "node_count": len(snapshot.nodes),
                "edge_count": len(snapshot.edges),
            },
        )

        return {
            "generation_id": generation_id,
            "status": "completed",
            "user_id": user_id,
            "video_id": video_id,
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
        }
    except Exception as exc:
        logger.exception(
            "Failed to generate idea graph for user=%s video=%s",
            user_id,
            video_id,
        )
        set_idea_graph_generation_status(
            user_id=user_id,
            video_id=video_id,
            status=IdeaGraphGenerationStatus.FAILED,
            error=str(exc),
        )
        event_store.mark_failed(generation_id, error=str(exc))
        raise
