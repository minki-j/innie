"""
Main Prefect flow: YouTube Video Pipeline (funnel-aware).

For each active funnel:
  1. Discover new videos (keyword search + creator scraping)
  2. Fetch metadata / transcript / summary for each new video
  3. Save videos to DB and link to the funnel
  4. Call the classify_items LangGraph agent to route videos into ClassNodes
  5. Save ClassNodeResults for each video × ClassNode classification
  6. Update lastPipelineRunAt on the funnel

Triggering semantics:
  - funnel_id=None  → process all active funnels that are due
  - funnel_id=X     → process that specific funnel (ignores interval)
"""

from __future__ import annotations

import logging
from typing import Any

from prefect import flow, get_run_logger

from config import (
    CLASSIFY_MAJORITY_THRESHOLD,
    CLASSIFY_MODELS,
    CLASSIFY_TOTAL_INVOCATIONS,
    LANGGRAPH_API_KEY,
    LANGGRAPH_API_URL,
)
from models.schemas import (
    ClassNodeModelVerdictCreate,
    ClassNodeResultCreate,
    ClassNodeResultValue,
    ClassNodeWithRelations,
    FunnelWithRelations,
    VideoData,
)
from tasks.db import (
    class_node_result_exists,
    delete_stale_class_node_results,
    ensure_llms_exist,
    get_active_funnels,
    get_funnel_by_id,
    get_funnel_video_ids,
    get_video_data,
    get_videos_for_funnel,
    link_video_to_funnel,
    save_class_node_model_verdicts,
    save_class_node_result,
    save_video,
    update_funnel_last_run,
    video_exists,
)
from tasks.evaluate import generate_summary
from tasks.youtube import (
    fetch_creator_videos,
    fetch_transcript,
    fetch_video_metadata,
    search_videos_by_keyword,
)

logging.basicConfig(level=logging.INFO)


# ── LangGraph classify helper ─────────────────────────────────


def _build_item_content(video: VideoData) -> str:
    """Format a VideoData into a plain-text item for the LLM classifier."""
    parts = [f"Title: {video.title}"]
    if video.channel_title:
        parts.append(f"Channel: {video.channel_title}")
    if video.summary:
        parts.append(f"Summary: {video.summary}")
    elif video.description:
        parts.append(f"Description: {video.description[:800]}")
    return "\n".join(parts)


def _extract_video_id_from_url(url: str) -> str | None:
    import re

    m = re.search(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        url,
    )
    return m.group(1) if m else None


def _save_results_for_video(
    video_id: str,
    data: dict,
    logger: Any,
    skip_existing: bool = False,
) -> None:
    """Save ClassNodeResult + ClassNodeModelVerdict rows for a single video."""
    pass_node_ids = {nd["node_id"] for nd in data["classified_as"]}
    all_verdict_node_ids = {v["node_id"] for v in data["verdicts"]}
    fail_node_ids = all_verdict_node_ids - pass_node_ids

    # Ensure all referenced LLM rows exist before inserting verdicts
    unique_llm_ids = list({v["model"] for v in data["verdicts"]})
    if unique_llm_ids:
        ensure_llms_exist(unique_llm_ids)

    def _save_node(
        class_node_id: str, result_value: ClassNodeResultValue, node_data: dict | None
    ) -> None:
        if skip_existing and class_node_result_exists(video_id, class_node_id):
            return
        node_verdict_list = [
            v for v in data["verdicts"] if v["node_id"] == class_node_id
        ]
        pass_votes = sum(1 for v in node_verdict_list if v["verdict"])
        confidence_score = (
            node_data.get("confidence_score", 1.0)
            if node_data
            else (pass_votes / len(node_verdict_list) if node_verdict_list else 0.0)
        )
        try:
            result_id = save_class_node_result(
                ClassNodeResultCreate(
                    video_id=video_id,
                    class_node_id=class_node_id,
                    result=result_value,
                    confidence_score=confidence_score,
                    explanation=node_data.get("explanation") if node_data else None,
                )
            )
            if node_verdict_list:
                save_class_node_model_verdicts(
                    [
                        ClassNodeModelVerdictCreate(
                            video_id=video_id,
                            class_node_id=class_node_id,
                            class_node_result_id=result_id,
                            llm_id=v["model"],
                            rationale=v["rationale"],
                            verdict=v["verdict"],
                        )
                        for v in node_verdict_list
                    ]
                )
        except Exception:
            logger.exception(
                "Failed to save ClassNodeResult: video=%s class_node=%s",
                video_id,
                class_node_id,
            )

    for node_data in data["classified_as"]:
        _save_node(node_data["node_id"], ClassNodeResultValue.PASS, node_data)

    for node_id in fail_node_ids:
        _save_node(node_id, ClassNodeResultValue.FAIL, None)


def _classify_videos_via_langgraph(
    funnel: FunnelWithRelations,
    class_nodes: list[ClassNodeWithRelations],
    videos: list[VideoData],
    logger: Any,
) -> dict[str, dict]:
    """
    Call the deployed classify_items LangGraph agent.

    Returns a mapping of video_id → {
        "classified_as": list of {node_id, confidence_score, explanation},
        "verdicts":      list of {node_id, model, rationale, verdict},
    }

    The graph is called with:
      - taxonomy = funnel metadata
      - root_node_id = the agent's synthetic root node ID (agents/state.py ROOT_NODE_ID)
      - nodes = full ClassNode list as ClassNodeState objects, where top-level nodes
                point to the synthetic root as their parent
      - items = all videos as ItemState objects
    """
    from langgraph_sdk import get_sync_client

    if not class_nodes:
        logger.info(
            "Funnel '%s' has no class nodes — skipping LangGraph classification",
            funnel.name,
        )
        return {}

    if not videos:
        logger.info("No videos to classify for funnel '%s'", funnel.name)
        return {}

    # The agent always maintains a synthetic root node with this hardcoded ID
    # (defined as ROOT_NODE_ID in agents/state.py). Classification starts at this
    # root, so top-level class nodes must declare it as their parent_node_id.
    ROOT_NODE_ID = "root"

    nodes = []
    for cn in class_nodes:
        few_shot_items = []
        for gs in cn.gold_standards:
            vid_id = _extract_video_id_from_url(gs.video_url)
            if vid_id:
                few_shot_items.append(
                    {
                        "item_id": vid_id,
                        "confidence_score": 1.0,
                        "is_verified": True,
                        "used_as_few_shot_example": True,
                    }
                )

        nodes.append(
            {
                "id": cn.id,
                # Top-level class nodes (no DB parent) must point to the agent's
                # synthetic root so the agent can find them as children of root.
                "parent_node_id": cn.parent_class_node_id or ROOT_NODE_ID,
                "label": cn.title or cn.id,
                "description": cn.description or "",
                "items": few_shot_items,
            }
        )

    items = [
        {
            "id": v.video_id,
            "content": _build_item_content(v),
        }
        for v in videos
    ]

    graph_input = {
        "taxonomy": {
            "id": funnel.id,
            "name": funnel.name,
            "aspect": funnel.description or funnel.name,
            "rules": [],
        },
        "user_id": funnel.user_id,
        "models": CLASSIFY_MODELS,
        "total_invocations": CLASSIFY_TOTAL_INVOCATIONS,
        "majority_threshold": CLASSIFY_MAJORITY_THRESHOLD,
        "is_for_single_batch": True,
        "root_node_id": ROOT_NODE_ID,
        "nodes": nodes,
        "items": items,
    }

    logger.info(
        "Calling classify_items LangGraph agent: %d videos → %d class nodes (url=%s)",
        len(videos),
        len(nodes),
        LANGGRAPH_API_URL,
    )

    client = get_sync_client(
        url=LANGGRAPH_API_URL,
        api_key=LANGGRAPH_API_KEY or None,
    )
    thread = client.threads.create()
    run = client.runs.create(
        thread_id=thread["thread_id"],
        assistant_id="classify_items",
        input=graph_input,
    )
    client.runs.join(thread_id=thread["thread_id"], run_id=run["run_id"])

    state = client.threads.get_state(thread_id=thread["thread_id"])
    classified_items = state["values"].get("items", [])

    class_node_ids = {cn.id for cn in class_nodes}

    result: dict[str, dict] = {}
    for item in classified_items:
        video_id = item["id"]
        classified_as = [
            c
            for c in (item.get("classified_as") or [])
            if c["node_id"] in class_node_ids
        ]
        # Include all verdicts (PASS and FAIL) for nodes in this funnel
        verdicts = [
            v for v in (item.get("verdicts") or []) if v["node_id"] in class_node_ids
        ]
        if not classified_as and not verdicts:
            continue
        result[video_id] = {
            "classified_as": classified_as,
            "verdicts": verdicts,
        }

    logger.info(
        "LangGraph classified %d/%d videos into class nodes",
        len(result),
        len(videos),
    )
    return result


# ── Sub-flows ─────────────────────────────────────────────────


@flow(name="discover_videos", log_prints=True)
def discover_videos(funnel: FunnelWithRelations) -> list[str]:
    """
    Video discovery using keyword search and creator fetch (yt-dlp).
    """
    logger = get_run_logger()
    discovered: set[str] = set()

    for kw in funnel.keywords:
        video_ids = search_videos_by_keyword(
            kw.keyword, max_results=funnel.max_videos_per_keyword
        )
        discovered.update(video_ids)
        logger.info("Keyword '%s': found %d videos", kw.keyword, len(video_ids))

    for creator in funnel.creators:
        video_ids = fetch_creator_videos(
            channel_id=creator.channel_id,
            channel_url=creator.channel_url,
            months_back=creator.scrape_months_back,
            max_results=funnel.max_videos_per_creator,
        )
        discovered.update(video_ids)
        logger.info(
            "Creator '%s': found %d videos",
            creator.channel_name or creator.channel_id or creator.channel_url,
            len(video_ids),
        )

    logger.info(
        "Discovery for funnel '%s': %d total videos", funnel.name, len(discovered)
    )
    return list(discovered)


@flow(name="process_video_for_funnel", log_prints=True)
def process_video_for_funnel(
    video_id: str,
    funnel: FunnelWithRelations,
    model_name: str | None = None,
) -> VideoData | None:
    """
    Fetch / save a single video and link it to the funnel.
    Returns the VideoData on success (needed to build items for LangGraph).
    """
    logger = get_run_logger()
    logger.info("Processing video %s for funnel '%s'", video_id, funnel.name)

    existing_video = get_video_data(video_id) if video_exists(video_id) else None

    if existing_video is not None:
        logger.info(
            "Video %s already exists in DB, skipping metadata/transcript fetch",
            video_id,
        )
        video_data = existing_video
    else:
        video_data = fetch_video_metadata(video_id)
        if video_data is None:
            logger.warning("Could not fetch metadata for video %s, skipping", video_id)
            return None

        transcript_text, transcript_status = fetch_transcript(video_id)
        video_data.transcript = transcript_text
        video_data.transcript_status = transcript_status

        video_data.summary = generate_summary(video=video_data, model_name=model_name)

        save_video(video_data)

    link_video_to_funnel(video_id, funnel.id)

    return video_data


# ── Main flow ─────────────────────────────────────────────────


def _process_funnel(
    funnel: FunnelWithRelations,
    model_name: str | None,
    logger: Any,
    update_last_run: bool = True,
) -> None:
    """
    Process a full funnel:
    1. Discover new videos (keyword search + creator scraping)
    2. Save / link each video to the funnel
    3. Call classify_items_graph to route videos into ClassNodes
    4. Save ClassNodeResults for each classification
    5. Update lastPipelineRunAt
    """
    logger.info(
        "Processing funnel '%s' (%d keywords, %d creators, %d class nodes)",
        funnel.name,
        len(funnel.keywords),
        len(funnel.creators),
        len(funnel.class_nodes),
    )

    if not funnel.keywords and not funnel.creators and not funnel.description:
        logger.info(
            "Funnel '%s' has no keywords, creators, or description — skipping",
            funnel.name,
        )
        return

    # ── 1. Discover videos ────────────────────────────────────
    existing_funnel_video_ids = get_funnel_video_ids(funnel.id)
    discovered_ids = discover_videos(funnel)
    new_ids = [vid for vid in discovered_ids if vid not in existing_funnel_video_ids]

    logger.info(
        "Funnel '%s': %d discovered, %d new",
        funnel.name,
        len(discovered_ids),
        len(new_ids),
    )

    # ── 2. Save + link to funnel ──────────────────────────────
    saved_videos: list[VideoData] = []
    for video_id in new_ids:
        try:
            video_data = process_video_for_funnel(
                video_id=video_id,
                funnel=funnel,
                model_name=model_name,
            )
            if video_data:
                saved_videos.append(video_data)
        except Exception:
            logger.exception(
                "Failed to process video %s for funnel '%s'", video_id, funnel.name
            )

    if not funnel.class_nodes:
        logger.info(
            "Funnel '%s' has no class nodes — skipping classification step",
            funnel.name,
        )
        if update_last_run:
            update_funnel_last_run(funnel.id)
        return

    # ── 3. Call classify_items LangGraph agent ────────────────
    # Classify ALL videos in funnel (not just new ones) to handle re-runs cleanly
    all_funnel_videos = get_videos_for_funnel(funnel.id)

    try:
        classification_map = _classify_videos_via_langgraph(
            funnel=funnel,
            class_nodes=funnel.class_nodes,
            videos=all_funnel_videos,
            logger=logger,
        )
    except Exception:
        logger.exception(
            "LangGraph classification failed for funnel '%s' — skipping ClassNode results",
            funnel.name,
        )
        if update_last_run:
            update_funnel_last_run(funnel.id)
        return

    # ── 4. Save ClassNodeResults and per-model verdicts ───────
    for video_id, data in classification_map.items():
        _save_results_for_video(video_id, data, logger, skip_existing=True)

    if update_last_run:
        update_funnel_last_run(funnel.id)
    logger.info("Completed processing for funnel '%s'", funnel.name)


@flow(name="video_pipeline", log_prints=True)
def video_pipeline(
    model_name: str | None = None,
    funnel_id: str | None = None,
) -> None:
    """
    Main pipeline flow.

    Args:
        model_name: LLM model to use for ClassNode evaluation.
        funnel_id: If provided, process this specific funnel regardless of interval.
                   If None, process all active funnels that are due.
    """
    logger = get_run_logger()
    logger.info("Starting video pipeline (funnel_id=%s)", funnel_id)

    if funnel_id:
        funnel = get_funnel_by_id(funnel_id)
        if funnel is None:
            logger.error("Funnel %s not found", funnel_id)
            return
        logger.info("Manual trigger: funnel='%s' (%s)", funnel.name, funnel_id)
        _process_funnel(funnel, model_name, logger, update_last_run=True)
    else:
        funnels = get_active_funnels()
        logger.info("Found %d active funnels due for processing", len(funnels))

        if not funnels:
            logger.info("No funnels due for processing. Pipeline complete.")
            return

        for funnel in funnels:
            _process_funnel(funnel, model_name, logger, update_last_run=True)

    logger.info("Video pipeline complete")


@flow(name="re_evaluate_videos", log_prints=True)
def re_evaluate_videos(
    funnel_id: str,
    video_ids: list[str],
) -> None:
    """
    Re-classify selected videos against a funnel's current ClassNodes via LangGraph.

    Does NOT discover new videos. Runs LangGraph classification, saves results,
    then cleans up orphaned results.
    """
    logger = get_run_logger()
    logger.info("Re-evaluating %d videos for funnel %s", len(video_ids), funnel_id)

    funnel = get_funnel_by_id(funnel_id)
    if funnel is None:
        logger.error("Funnel %s not found", funnel_id)
        return

    if not funnel.class_nodes:
        logger.info("No class nodes for funnel '%s', nothing to evaluate", funnel.name)
        delete_stale_class_node_results(video_ids, funnel_id)
        return

    videos = [v for vid in video_ids if (v := get_video_data(vid)) is not None]
    missing = set(video_ids) - {v.video_id for v in videos}
    for vid in missing:
        logger.warning("Video %s not found in DB, skipping", vid)

    try:
        classification_map = _classify_videos_via_langgraph(
            funnel=funnel,
            class_nodes=funnel.class_nodes,
            videos=videos,
            logger=logger,
        )
    except Exception:
        logger.exception("LangGraph classification failed for funnel '%s'", funnel.name)
        delete_stale_class_node_results(video_ids, funnel_id)
        return

    for video_id, data in classification_map.items():
        _save_results_for_video(video_id, data, logger, skip_existing=False)

    delete_stale_class_node_results(video_ids, funnel_id)

    logger.info("Re-evaluation complete for funnel '%s'", funnel.name)


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    video_pipeline.from_source(
        source=str(Path(__file__).resolve().parent.parent),
        entrypoint="flows/video_pipeline.py:video_pipeline",
    ).serve(name="video-pipeline")
