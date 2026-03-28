"""
Integration test script for the build_idea_graph LangGraph graph.

Usage (from the orchestrator/ directory):
    uv run python scripts/test_build_idea_graph.py

Requires the LangGraph dev server to be running:
    cd agents && uv run dev
"""

from __future__ import annotations

import json
import logging

from langgraph_sdk import get_sync_client

from config import LANGGRAPH_API_KEY, LANGGRAPH_API_URL

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_build_idea_graph")


def main() -> None:
    transcript_segments = [
        {
            "text": "The speaker argues that remote work is most effective when teams default to written communication and document decisions clearly.",
            "start_sec": 0.0,
            "end_sec": 18.0,
        },
        {
            "text": "They support this claim with an example from a product team that reduced repeated meetings after introducing a shared written decision log.",
            "start_sec": 18.0,
            "end_sec": 36.0,
        },
        {
            "text": "A counterargument appears when the speaker notes that written communication can slow down fast-moving collaboration if everything becomes asynchronous.",
            "start_sec": 36.0,
            "end_sec": 54.0,
        },
        {
            "text": "The speaker then rebuts that point by saying teams should still switch to live conversation for ambiguity or conflict, but return to documentation afterward.",
            "start_sec": 54.0,
            "end_sec": 74.0,
        },
        {
            "text": "They conclude that the goal is not fewer conversations, but a better system for preserving context and decisions over time.",
            "start_sec": 74.0,
            "end_sec": 90.0,
        },
    ]
    transcript = " ".join(segment["text"] for segment in transcript_segments)

    client = get_sync_client(
        url=LANGGRAPH_API_URL,
        api_key=LANGGRAPH_API_KEY or None,
    )
    thread = client.threads.create()
    stream_events = []
    for part in client.runs.stream(
        thread_id=thread["thread_id"],
        assistant_id="build_idea_graph",
        input={
            "user_id": "test-user",
            "video_id": "test-video",
            "video_title": "Why remote work needs written communication",
            "transcript": transcript,
            "transcript_segments": transcript_segments,
            "current_graph": {"nodes": [], "edges": []},
        },
        stream_mode=["custom"],
        version="v2",
    ):
        if part.get("type") == "custom":
            stream_events.append(part.get("data"))
    state = client.threads.get_state(thread_id=thread["thread_id"])

    result_graph = state["values"].get("result_graph")
    if not result_graph:
        raise AssertionError("LangGraph did not return result_graph")

    nodes = result_graph.get("nodes", [])
    edges = result_graph.get("edges", [])
    assert len(nodes) >= 3, f"Expected at least 3 nodes, got {len(nodes)}"
    assert len(edges) >= 2, f"Expected at least 2 edges, got {len(edges)}"
    assert any(node.get("transcript_sources") for node in nodes), "Expected at least one node with transcript sources"
    assert stream_events, "Expected at least one custom stream event"
    assert any(event.get("event_type") == "node_added" for event in stream_events), "Expected node_added stream events"

    print("\n" + "=" * 60)
    print("Idea graph generation result")
    print("=" * 60)
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")
    print(f"Custom stream events: {len(stream_events)}")
    print(json.dumps(result_graph, indent=2))


if __name__ == "__main__":
    main()
