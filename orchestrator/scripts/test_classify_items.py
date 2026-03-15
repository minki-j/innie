"""
Test script: trigger the classify_items LangGraph graph directly.

Builds sample funnel + video data (no DB, no Prefect) and calls
_classify_videos_via_langgraph, then prints the classification results.

Usage (from the orchestrator/ directory):
    uv run python scripts/test_classify_items.py

Requires the LangGraph dev server to be running:
    cd agents && uv run dev
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Allow imports from the orchestrator root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flows.video_pipeline import _classify_videos_via_langgraph
from models.schemas import (
    ClassNodeWithRelations,
    FunnelWithRelations,
    GoldStandardWithContext,
    VideoData,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_classify_items")


# ── Sample taxonomy ────────────────────────────────────────────
#
# The LangGraph graph expects a single-root tree:
#   NODE_ROOT  (parentClassNodeId=None)  ← root_node_id
#   ├── NODE_TUTORIALS   (parentClassNodeId=NODE_ROOT)
#   ├── NODE_PRODUCT_REVIEWS (parentClassNodeId=NODE_ROOT)
#   └── NODE_VLOGS       (parentClassNodeId=NODE_ROOT)
#
# The `classify` subgraph looks for nodes whose parent_node_id == root_node_id,
# so the category nodes MUST be children of the root, not siblings.

FUNNEL_ID = "test-funnel-001"
USER_ID = "test-user-001"

NODE_ROOT = "node-root"
NODE_TUTORIALS = "node-tutorials"
NODE_PRODUCT_REVIEWS = "node-product-reviews"
NODE_VLOGS = "node-vlogs"

sample_funnel = FunnelWithRelations(
    id=FUNNEL_ID,
    name="Tech YouTube Content",
    description="Videos about software engineering, tools, and tech products",
    userId=USER_ID,
    active=True,
    keywords=[],
    creators=[],
    class_nodes=[],  # populated below
)

sample_class_nodes: list[ClassNodeWithRelations] = [
    # Root node — the entry point for the graph
    ClassNodeWithRelations(
        id=NODE_ROOT,
        description=(
            "Tech YouTube Content\n"
            "Top-level category for all tech and software engineering YouTube videos."
        ),
        parentClassNodeId=None,
        funnelId=FUNNEL_ID,
        children=[],
        gold_standards=[],
    ),
    # Level-1 children of the root
    ClassNodeWithRelations(
        id=NODE_TUTORIALS,
        description=(
            "Tutorial / How-to videos\n"
            "Videos that teach the viewer how to do something step by step, "
            "such as coding tutorials, tool walkthroughs, or setup guides."
        ),
        parentClassNodeId=NODE_ROOT,
        funnelId=FUNNEL_ID,
        children=[],
        gold_standards=[
            GoldStandardWithContext(
                id="gs-t-1",
                classNodeId=NODE_TUTORIALS,
                videoUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                isPositive=True,
                video_summary="Step-by-step guide to setting up a Python virtual environment",
            ),
        ],
    ),
    ClassNodeWithRelations(
        id=NODE_PRODUCT_REVIEWS,
        description=(
            "Product / Tool reviews\n"
            "Videos that review a software product, hardware device, or developer "
            "tool, including comparisons and first-impressions."
        ),
        parentClassNodeId=NODE_ROOT,
        funnelId=FUNNEL_ID,
        children=[],
        gold_standards=[
            GoldStandardWithContext(
                id="gs-r-1",
                classNodeId=NODE_PRODUCT_REVIEWS,
                videoUrl="https://www.youtube.com/watch?v=9bZkp7q19f0",
                isPositive=True,
                video_summary="Honest review of the new MacBook Pro M3 for developers",
            ),
        ],
    ),
    ClassNodeWithRelations(
        id=NODE_VLOGS,
        description=(
            "Developer / tech vlogs\n"
            "Day-in-the-life or vlog-style videos from developers or tech creators "
            "that are not primarily instructional or review content."
        ),
        parentClassNodeId=NODE_ROOT,
        funnelId=FUNNEL_ID,
        children=[],
        gold_standards=[],
    ),
]

sample_funnel.class_nodes = sample_class_nodes

# ── Sample videos ──────────────────────────────────────────────

sample_videos: list[VideoData] = [
    VideoData(
        video_id="vid-001",
        title="Build a REST API with FastAPI in 30 minutes",
        channel_title="CodeWithMe",
        summary=(
            "A beginner-friendly walkthrough showing how to create a REST API "
            "from scratch using FastAPI, including routing, request validation, "
            "and running the dev server."
        ),
    ),
    VideoData(
        video_id="vid-002",
        title="I tested every AI coding assistant — here's the verdict",
        channel_title="DevGadgetReviews",
        summary=(
            "Comprehensive comparison of GitHub Copilot, Cursor, and Codeium "
            "across real-world coding tasks. Pros, cons, and pricing breakdown."
        ),
    ),
    VideoData(
        video_id="vid-003",
        title="A week in my life as a senior software engineer at a startup",
        channel_title="EngineerLife",
        summary=(
            "Vlog-style video following a senior engineer through meetings, code "
            "reviews, and side projects over a typical work week."
        ),
    ),
    VideoData(
        video_id="vid-004",
        title="Docker Compose explained: multi-service apps made easy",
        channel_title="ContainerPros",
        summary=(
            "Tutorial explaining Docker Compose concepts with a hands-on demo: "
            "setting up a web app with a database and Redis cache using a single "
            "docker-compose.yml file."
        ),
    ),
]


# ── Run ────────────────────────────────────────────────────────

def main() -> None:
    from config import LANGGRAPH_API_URL

    print(f"LangGraph URL: {LANGGRAPH_API_URL}")
    print(f"Classifying {len(sample_videos)} videos into {len(sample_class_nodes)} class nodes\n")

    result = _classify_videos_via_langgraph(
        funnel=sample_funnel,
        class_nodes=sample_class_nodes,
        videos=sample_videos,
        logger=logger,
    )

    print("\n" + "=" * 60)
    print("Classification results")
    print("=" * 60)

    node_labels = {cn.id: cn.description.split("\n")[0] for cn in sample_class_nodes}
    video_titles = {v.video_id: v.title for v in sample_videos}

    if not result:
        print("No videos were classified.")
        return

    for video_id, node_ids in result.items():
        title = video_titles.get(video_id, video_id)
        labels = [node_labels.get(nid, nid) for nid in node_ids]
        print(f"\n  Video : {title} ({video_id})")
        print(f"  Nodes : {', '.join(labels)}")

    print("\n" + "=" * 60)
    print("Raw mapping (video_id → [class_node_id, ...]):")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
