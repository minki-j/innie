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
import time
from datetime import datetime, timezone
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.task_runners import ThreadPoolTaskRunner

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
    bulk_check_existing_class_node_results,
    bulk_save_class_node_results,
    delete_stale_class_node_results,
    ensure_llms_exist,
    get_funnels_due_for_pipeline,
    get_funnel_by_id,
    get_funnel_video_ids,
    get_video_data,
    get_unclassified_videos_for_funnel,
    link_video_to_funnel,
    save_class_node_model_verdicts,
    save_video,
    update_funnel_last_run,
    video_exists,
)
from tasks.evaluate import generate_summary
from tasks.youtube import (
    fetch_creator_videos,
    fetch_transcript,
    fetch_video_metadata,
    fetch_video_metadata_batch,
    search_videos_by_keyword_google_or_yt_dlp,
)
from utils.failed_queue import get_failed_queue
from utils.rate_limiter import get_rate_limiter

logging.basicConfig(level=logging.INFO)

_VIDEO_PROCESSING_MAX_WORKERS = 4


# ── on_failure hooks ──────────────────────────────────────────


def _on_video_processing_failure(flow, flow_run, state) -> None:
    """Push failed process_video_for_funnel jobs to the dead-letter queue."""
    exc = state.result(raise_on_failure=False)
    params = flow_run.parameters or {}
    try:
        get_failed_queue("process_video_for_funnel").push(
            {
                "video_id": params.get("video_id"),
                "funnel_id": (params.get("funnel") or {}).get("id"),
                "model_name": params.get("model_name"),
                "error": str(exc),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to push video processing failure to dead-letter queue"
        )


def _on_langgraph_classify_failure(flow, flow_run, state) -> None:
    """Push failed video_pipeline classification runs to the dead-letter queue."""
    exc = state.result(raise_on_failure=False)
    params = flow_run.parameters or {}
    try:
        get_failed_queue("langgraph_classify").push(
            {
                "funnel_id": params.get("funnel_id"),
                "model_name": params.get("model_name"),
                "error": str(exc),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to push LangGraph classification failure to dead-letter queue"
        )


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


def _save_all_results(
    classification_map: dict[str, dict],
    logger: Any,
    skip_existing: bool = False,
) -> None:
    """
    Bulk-save ClassNodeResult + ClassNodeModelVerdict rows for all videos at once.

    Reduces DB round-trips from O(N×M) to O(1) by batching all inserts across
    every video and class node into a handful of bulk queries.
    """
    # ── 1. Ensure LLM rows exist (one call for all videos) ────────
    all_llm_ids = {
        v["model"] for data in classification_map.values() for v in data["verdicts"]
    }
    if all_llm_ids:
        ensure_llms_exist(list(all_llm_ids))

    # ── 2. Build all ClassNodeResultCreate records ─────────────────
    all_results: list[ClassNodeResultCreate] = []
    # verdict_index lets us look up verdicts by (video_id, class_node_id) later
    verdict_index: dict[tuple[str, str], list[dict]] = {}

    for video_id, data in classification_map.items():
        pass_node_ids = {nd["node_id"] for nd in data["classified_as"]}
        all_verdict_node_ids = {v["node_id"] for v in data["verdicts"]}
        fail_node_ids = all_verdict_node_ids - pass_node_ids

        for nd in data["classified_as"]:
            node_id = nd["node_id"]
            node_verdicts = [v for v in data["verdicts"] if v["node_id"] == node_id]
            verdict_index[(video_id, node_id)] = node_verdicts
            all_results.append(
                ClassNodeResultCreate(
                    video_id=video_id,
                    class_node_id=node_id,
                    result=ClassNodeResultValue.PASS,
                    confidence_score=nd.get("confidence_score", 1.0),
                    explanation=nd.get("explanation"),
                )
            )

        for node_id in fail_node_ids:
            node_verdicts = [v for v in data["verdicts"] if v["node_id"] == node_id]
            pass_votes = sum(1 for v in node_verdicts if v["verdict"])
            confidence_score = pass_votes / len(node_verdicts) if node_verdicts else 0.0
            verdict_index[(video_id, node_id)] = node_verdicts
            all_results.append(
                ClassNodeResultCreate(
                    video_id=video_id,
                    class_node_id=node_id,
                    result=ClassNodeResultValue.FAIL,
                    confidence_score=confidence_score,
                    explanation=None,
                )
            )

    # ── 3. Filter out already-saved pairs (one bulk check) ────────
    if skip_existing and all_results:
        pairs = [(r.video_id, r.class_node_id) for r in all_results]
        existing = bulk_check_existing_class_node_results(pairs)
        all_results = [
            r for r in all_results if (r.video_id, r.class_node_id) not in existing
        ]

    if not all_results:
        logger.info("_save_all_results: all results already exist, nothing to save")
        return

    # ── 4. Bulk-insert ClassNodeResults, get back (video_id, class_node_id) → id ──
    try:
        result_id_map = bulk_save_class_node_results(all_results)
    except Exception:
        logger.exception("Failed to bulk-save ClassNodeResults")
        return

    # ── 5. Build and bulk-insert all verdicts (one call) ─────────
    all_verdicts: list[ClassNodeModelVerdictCreate] = []
    for (video_id, class_node_id), result_id in result_id_map.items():
        for v in verdict_index.get((video_id, class_node_id), []):
            all_verdicts.append(
                ClassNodeModelVerdictCreate(
                    video_id=video_id,
                    class_node_id=class_node_id,
                    class_node_result_id=result_id,
                    llm_id=v["model"],
                    rationale=v["rationale"],
                    verdict=v["verdict"],
                )
            )

    if all_verdicts:
        save_class_node_model_verdicts(all_verdicts)
    else:
        logger.info("skipped save_class_node_model_verdicts: no verdicts to save")


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

    get_rate_limiter("langgraph").acquire()

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
    Video discovery using keyword search and creator fetch.

    Keyword search is bounded by the last pipeline run timestamp and the current
    time so only newly published videos are returned on incremental runs. On the
    first run (no last_pipeline_run_at), no keyword date filter is applied.
    """
    logger = get_run_logger()
    discovered: set[str] = set()

    now = datetime.now(timezone.utc)
    published_after: datetime | None = None
    published_before: datetime | None = None

    if funnel.last_pipeline_run_at:
        last_run = funnel.last_pipeline_run_at
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        published_after = last_run
        published_before = now
        logger.info(
            "Keyword search time range: %s -> %s",
            published_after.isoformat(),
            published_before.isoformat(),
        )
    else:
        logger.info(
            "First run for funnel '%s' - no keyword date filter applied",
            funnel.name,
        )

    for kw in funnel.keywords:
        video_ids = search_videos_by_keyword_google_or_yt_dlp(
            kw.keyword,
            max_results=funnel.max_videos_per_keyword,
            published_after=published_after,
            published_before=published_before,
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


@flow(
    name="process_video_for_funnel",
    log_prints=True,
    on_failure=[_on_video_processing_failure],
)
def process_video_for_funnel(
    video_id: str,
    funnel: FunnelWithRelations,
    model_name: str | None = None,
    prefetched_video_data: VideoData | None = None,
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
        video_data = prefetched_video_data or fetch_video_metadata(video_id)
        if video_data is None:
            logger.warning(
                "Could not fetch metadata for video %s from YouTube API, skipping",
                video_id,
            )
            return None

        transcript_text, transcript_status = fetch_transcript(video_id)
        video_data.transcript = transcript_text
        video_data.transcript_status = transcript_status

        video_data.summary = generate_summary(video=video_data, model_name=model_name)

        save_video(video_data)

    link_video_to_funnel(video_id, funnel.id)

    return video_data


@task(name="submit_process_video_for_funnel")
def _submit_process_video_for_funnel(
    video_id: str,
    funnel: FunnelWithRelations,
    model_name: str | None = None,
    prefetched_video_data: VideoData | None = None,
) -> VideoData | None:
    return process_video_for_funnel(
        video_id=video_id,
        funnel=funnel,
        model_name=model_name,
        prefetched_video_data=prefetched_video_data,
    )


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
    t0 = time.perf_counter()
    existing_funnel_video_ids = get_funnel_video_ids(funnel.id)
    discovered_ids = discover_videos(funnel)
    new_ids = [vid for vid in discovered_ids if vid not in existing_funnel_video_ids]
    logger.info(
        "Step 1 (discover videos) took %.2fs — %d discovered, %d new",
        time.perf_counter() - t0,
        len(discovered_ids),
        len(new_ids),
    )

    # ── 2. Save + link to funnel ──────────────────────────────
    # Use a thread pool -- .submit() from prefect -- to process videos in parallel.
    t0 = time.perf_counter()
    saved_videos: list[VideoData] = []
    prefetched_video_map = fetch_video_metadata_batch(new_ids) if new_ids else {}
    submitted_video_runs = {
        video_id: _submit_process_video_for_funnel.submit(
            video_id=video_id,
            funnel=funnel,
            model_name=model_name,
            prefetched_video_data=prefetched_video_map.get(video_id),
        )
        for video_id in new_ids
    }
    for video_id, future in submitted_video_runs.items():
        try:
            video_data = future.result()
            if video_data:
                saved_videos.append(video_data)
        except Exception:
            logger.exception(
                "Failed to process video %s for funnel '%s'", video_id, funnel.name
            )
    logger.info(
        "Step 2 (save + link videos) took %.2fs — %d saved",
        time.perf_counter() - t0,
        len(saved_videos),
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
    _MAX_CLASSIFICATION_VIDEOS = 100
    class_node_ids = [cn.id for cn in funnel.class_nodes]

    # Oldest-first unclassified videos, capped at the max
    unclassified_videos = get_unclassified_videos_for_funnel(
        funnel_id=funnel.id,
        class_node_ids=class_node_ids,
        limit=_MAX_CLASSIFICATION_VIDEOS - len(saved_videos),
    )

    # Newly saved videos must always be processed — add any that weren't in the
    # oldest-first batch (they'd be at the tail and could have been cut by LIMIT)
    unclassified_ids = {v.video_id for v in unclassified_videos}
    extra_saved = [v for v in saved_videos if v.video_id not in unclassified_ids]
    if extra_saved:
        slots = max(0, _MAX_CLASSIFICATION_VIDEOS - len(extra_saved))
        videos_to_classify = unclassified_videos[:slots] + extra_saved
    else:
        videos_to_classify = unclassified_videos

    logger.info(
        "Step 3 candidates: %d unclassified (oldest-first) + %d forced-new = %d total",
        len(unclassified_videos) - len(extra_saved),
        len(extra_saved),
        len(videos_to_classify),
    )

    t0 = time.perf_counter()
    try:
        classification_map = _classify_videos_via_langgraph(
            funnel=funnel,
            class_nodes=funnel.class_nodes,
            videos=videos_to_classify,
            logger=logger,
        )
        logger.info(
            "Step 3 (LangGraph classification) took %.2fs — %d videos classified",
            time.perf_counter() - t0,
            len(classification_map),
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
    t0 = time.perf_counter()
    _save_all_results(classification_map, logger, skip_existing=True)
    logger.info("Step 4 (save results) took %.2fs", time.perf_counter() - t0)

    # ── 5. Update lastPipelineRunAt ───────────────────────────
    if update_last_run:
        t0 = time.perf_counter()
        update_funnel_last_run(funnel.id)
        logger.info("Step 5 (update last run) took %.2fs", time.perf_counter() - t0)
    logger.info("Completed processing for funnel '%s'", funnel.name)


@flow(
    name="video_pipeline",
    log_prints=True,
    on_failure=[_on_langgraph_classify_failure],
    task_runner=ThreadPoolTaskRunner(max_workers=_VIDEO_PROCESSING_MAX_WORKERS),
)
def video_pipeline(
    model_name: str | None = None,
    funnel_id: str | None = None,
) -> None:
    """
    Main pipeline flow.

    Args:
        model_name: LLM model to use for ClassNode evaluation.
        funnel_id: If provided, process this specific funnel, skipping due date check.
                   If None, process all funnels that are due for pipeline run.
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
        funnels = get_funnels_due_for_pipeline()
        logger.info("Found %d funnels due for pipeline run", len(funnels))

        if not funnels:
            logger.info("No funnels due for pipeline run. Pipeline complete.")
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

    _save_all_results(classification_map, logger, skip_existing=False)

    delete_stale_class_node_results(video_ids, funnel_id)

    logger.info("Re-evaluation complete for funnel '%s'", funnel.name)


# ── Retry failed jobs ─────────────────────────────────────────


@flow(name="retry_failed_jobs", log_prints=True)
def retry_failed_jobs(queue_names: list[str] | None = None) -> None:
    """
    Drain Redis dead-letter queues and re-process each failed item.

    Args:
        queue_names: Specific queue names to drain. Defaults to all known queues:
                     ``process_video_for_funnel``, ``evaluate_class_node``,
                     ``langgraph_classify``.
    """
    logger = get_run_logger()

    all_queues = [
        "process_video_for_funnel",
        "evaluate_class_node",
        "langgraph_classify",
    ]
    targets = queue_names or all_queues

    for qname in targets:
        queue = get_failed_queue(qname)
        jobs = queue.pop_all()
        if not jobs:
            logger.info("Dead-letter queue '%s' is empty", qname)
            continue

        logger.info("Retrying %d failed jobs from queue '%s'", len(jobs), qname)

        if qname == "process_video_for_funnel":
            for job in jobs:
                video_id = job.get("video_id")
                funnel_id = job.get("funnel_id")
                model_name = job.get("model_name")
                if not video_id or not funnel_id:
                    logger.warning("Skipping malformed job: %s", job)
                    continue
                funnel = get_funnel_by_id(funnel_id)
                if funnel is None:
                    logger.warning(
                        "Funnel %s not found, skipping video %s", funnel_id, video_id
                    )
                    continue
                logger.info(
                    "Re-processing video %s for funnel '%s'", video_id, funnel.name
                )
                process_video_for_funnel(
                    video_id=video_id, funnel=funnel, model_name=model_name
                )

        elif qname == "langgraph_classify":
            # Re-trigger the full pipeline for the affected funnels (deduped)
            seen: set[str] = set()
            for job in jobs:
                funnel_id = job.get("funnel_id")
                model_name = job.get("model_name")
                if not funnel_id or funnel_id in seen:
                    continue
                seen.add(funnel_id)
                logger.info("Re-triggering pipeline for funnel %s", funnel_id)
                video_pipeline(model_name=model_name, funnel_id=funnel_id)

        elif qname == "evaluate_class_node":
            # evaluate_class_node failures don't carry a funnel_id, so we cannot
            # auto-route them to re_evaluate_videos. Log each failure clearly so
            # an operator can trigger re_evaluate_videos manually if needed.
            for job in jobs:
                logger.warning(
                    "Unresolved evaluate_class_node failure — "
                    "video_id=%s class_node_id=%s model=%s error=%s failed_at=%s. "
                    "Trigger re_evaluate_videos manually to retry.",
                    job.get("video_id"),
                    job.get("class_node_id"),
                    job.get("model_name"),
                    job.get("error"),
                    job.get("failed_at"),
                )


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    video_pipeline.from_source(
        source=str(Path(__file__).resolve().parent.parent),
        entrypoint="flows/video_pipeline.py:video_pipeline",
    ).serve(name="video-pipeline")
