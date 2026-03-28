from __future__ import annotations

import logging
from typing import Any

from langgraph_sdk import get_sync_client

from config import LANGGRAPH_API_KEY, LANGGRAPH_API_URL
from models.schemas import IdeaGraphGenerationInput, IdeaGraphGenerationStatus, IdeaGraphSnapshot
from tasks.db import (
    get_idea_graph_snapshot,
    get_video_for_idea_graph,
    replace_idea_graph,
    set_idea_graph_generation_status,
)
from tasks.youtube import fetch_transcript_segments
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def generate_idea_graph_for_video(
    user_id: str,
    video_id: str,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """
    Generate an idea graph for a specific user/video pair via LangGraph.

    The LangGraph agent reads transcript chunks and the current graph state, then
    returns a full replacement graph snapshot.
    """
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
        run = client.runs.create(
            thread_id=thread["thread_id"],
            assistant_id="build_idea_graph",
            input=graph_input.model_dump(mode="json"),
        )
        client.runs.join(thread_id=thread["thread_id"], run_id=run["run_id"])

        state = client.threads.get_state(thread_id=thread["thread_id"])
        result_graph = state["values"].get("result_graph")
        if not result_graph:
            raise ValueError("LangGraph did not return result_graph")

        snapshot = IdeaGraphSnapshot.model_validate(result_graph)
        replace_idea_graph(user_id=user_id, video_id=video_id, snapshot=snapshot)
        set_idea_graph_generation_status(
            user_id=user_id,
            video_id=video_id,
            status=IdeaGraphGenerationStatus.COMPLETED,
            error=None,
        )

        return {
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
        raise
