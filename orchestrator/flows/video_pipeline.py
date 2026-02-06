"""
Main Prefect flow: YouTube Video Pipeline.

Polls the DB for active topics, scrapes YouTube for new videos,
fetches transcripts, evaluates criteria with LLMs, and saves results.
"""

from __future__ import annotations

import logging
from typing import Any

from prefect import flow, get_run_logger

from models.schemas import GoldStandardWithContext, Topic, VideoData
from tasks.db import (
    criterion_result_exists,
    delete_stale_criterion_results,
    get_active_topics,
    get_gold_standard_video_data,
    get_topic_by_id,
    get_topic_video_ids,
    get_video_data,
    link_video_to_topic,
    save_criterion_result,
    save_video,
    update_topic_last_run,
    video_exists,
)
from tasks.evaluate import evaluate_criterion, generate_summary
from tasks.agi_search import search_videos_with_agi
from tasks.youtube import (
    fetch_creator_videos,
    fetch_transcript,
    fetch_video_metadata,
    search_videos_by_keyword,
)

logging.basicConfig(level=logging.INFO)


# ── Sub-flows ─────────────────────────────────────────────────


@flow(name="discover_videos_fast")
def discover_videos_fast(topic: Topic) -> list[str]:
    """
    Fast video discovery using keyword search and creator fetch (yt-dlp).
    Does NOT include AGI search (which is slow and runs separately).
    Returns a deduplicated list of video IDs.
    """
    logger = get_run_logger()
    discovered: set[str] = set()

    # Search by keywords
    for kw in topic.keywords:
        video_ids = search_videos_by_keyword(kw.keyword)
        discovered.update(video_ids)
        logger.info("Keyword '%s': found %d videos", kw.keyword, len(video_ids))

    # Fetch from creators
    for creator in topic.creators:
        video_ids = fetch_creator_videos(
            channel_id=creator.channel_id,
            channel_url=creator.channel_url,
            months_back=creator.scrape_months_back,
        )
        discovered.update(video_ids)
        logger.info(
            "Creator '%s': found %d videos",
            creator.channel_name or creator.channel_id or creator.channel_url,
            len(video_ids),
        )

    logger.info("Fast discovery for topic '%s': %d videos", topic.name, len(discovered))
    return list(discovered)


@flow(name="process_video_for_topic")
def process_video_for_topic(
    video_id: str,
    topic: Topic,
    model_name: str | None = None,
    few_shot_examples: list[tuple[GoldStandardWithContext, VideoData]] | None = None,
) -> None:
    """
    Process a single video for a topic:
    1. Fetch metadata (if not already in DB)
    2. Fetch transcript
    3. Generate summary (LLM)
    4. Save video to DB
    5. Link to topic
    6. Evaluate each criterion (with few-shot examples from gold standards)
    7. Save criterion results
    """
    logger = get_run_logger()
    logger.info("Processing video %s for topic '%s'", video_id, topic.name)

    # 1. Check if video already exists in DB to avoid redundant API calls
    existing_video = get_video_data(video_id) if video_exists(video_id) else None

    if existing_video is not None:
        logger.info("Video %s already exists in DB, skipping metadata/transcript fetch", video_id)
        video_data = existing_video
    else:
        # 2. Fetch metadata from YouTube
        video_data = fetch_video_metadata(video_id)
        if video_data is None:
            logger.warning("Could not fetch metadata for video %s, skipping", video_id)
            return

        # 3. Fetch transcript
        transcript_text, transcript_status = fetch_transcript(video_id)
        video_data.transcript = transcript_text
        video_data.transcript_status = transcript_status

        # 4. Generate summary from metadata + transcript
        video_data.summary = generate_summary(
            video=video_data,
            model_name=model_name,
        )

        # 5. Save video to DB
        save_video(video_data)

    # 6. Link video to topic
    link_video_to_topic(video_id, topic.id)

    # 7. Evaluate each criterion and save results
    if not topic.criteria:
        logger.info("No criteria for topic '%s', skipping evaluation", topic.name)
        return

    for criterion in topic.criteria:
        # Skip if already evaluated
        if criterion_result_exists(video_id, criterion.id):
            logger.info(
                "Criterion result already exists: video=%s criterion=%s, skipping",
                video_id,
                criterion.id,
            )
            continue

        result = evaluate_criterion(
            video=video_data,
            criterion=criterion,
            model_name=model_name,
            few_shot_examples=few_shot_examples,
        )
        save_criterion_result(result)


# ── Main flow ─────────────────────────────────────────────────


def _process_topic(topic: Topic, model_name: str | None, logger: Any) -> None:
    """Process a single topic: discover videos, fetch metadata, evaluate criteria."""
    logger.info(
        "Processing topic '%s' (%d keywords, %d creators, %d criteria)",
        topic.name,
        len(topic.keywords),
        len(topic.creators),
        len(topic.criteria),
    )

    # Skip topics with no keywords, no creators, and no description
    if not topic.keywords and not topic.creators and not topic.description:
        logger.info(
            "Topic '%s' has no keywords, creators, or description, skipping",
            topic.name,
        )
        return

    existing_video_ids = get_topic_video_ids(topic.id)
    logger.info("Topic '%s' already has %d videos", topic.name, len(existing_video_ids))

    # Fetch gold standard few-shot examples once for the whole topic
    few_shot_examples = get_gold_standard_video_data(topic.id)
    if few_shot_examples:
        logger.info(
            "Loaded %d gold standard few-shot examples for topic '%s'",
            len(few_shot_examples),
            topic.name,
        )

    # ── Phase 1: Fire AGI search in background, run fast searches,
    #             and process fast results immediately ──────────
    agi_future = search_videos_with_agi.submit(topic)

    fast_ids = discover_videos_fast(topic)
    fast_new = [vid for vid in fast_ids if vid not in existing_video_ids]

    if fast_new:
        logger.info(
            "Processing %d videos from fast search for topic '%s'",
            len(fast_new),
            topic.name,
        )
    for video_id in fast_new:
        try:
            process_video_for_topic(
                video_id=video_id,
                topic=topic,
                model_name=model_name,
                few_shot_examples=few_shot_examples,
            )
        except Exception:
            logger.exception(
                "Failed to process video %s for topic '%s'",
                video_id,
                topic.name,
            )

    # ── Phase 2: Collect AGI results and process any new ones ──
    try:
        agi_ids = agi_future.result()
        already_seen = existing_video_ids | set(fast_new)
        agi_new = [vid for vid in agi_ids if vid not in already_seen]

        if agi_new:
            logger.info(
                "Processing %d additional videos from AGI search for topic '%s'",
                len(agi_new),
                topic.name,
            )
        for video_id in agi_new:
            try:
                process_video_for_topic(
                    video_id=video_id,
                    topic=topic,
                    model_name=model_name,
                    few_shot_examples=few_shot_examples,
                )
            except Exception:
                logger.exception(
                    "Failed to process video %s for topic '%s'",
                    video_id,
                    topic.name,
                )
    except Exception:
        logger.warning(
            "AGI search failed for topic '%s', continuing without AGI results",
            topic.name,
        )

    # Update lastPipelineRunAt after successfully processing the topic
    update_topic_last_run(topic.id)
    logger.info("Updated lastPipelineRunAt for topic '%s'", topic.name)


@flow(name="video_pipeline", log_prints=True)
def video_pipeline(
    model_name: str | None = None,
    topic_id: str | None = None,
) -> None:
    """
    Main pipeline flow.

    Args:
        model_name: LLM model to use for criterion evaluation.
        topic_id: If provided, process only this specific topic (manual trigger).
                  If None, process all active topics that are due based on their
                  pipelineIntervalHours setting.
    """
    logger = get_run_logger()
    logger.info("Starting video pipeline (topic_id=%s)", topic_id)

    if topic_id:
        # Manual trigger: process a single topic regardless of interval
        topic = get_topic_by_id(topic_id)
        if topic is None:
            logger.error("Topic %s not found", topic_id)
            return
        logger.info("Manual trigger for topic '%s'", topic.name)
        _process_topic(topic, model_name, logger)
    else:
        # Scheduled run: get all active topics that are due
        topics = get_active_topics()
        logger.info("Found %d active topics due for processing", len(topics))

        if not topics:
            logger.info("No topics due for processing. Pipeline complete.")
            return

        for topic in topics:
            _process_topic(topic, model_name, logger)

    logger.info("Video pipeline complete")


@flow(name="re_evaluate_videos", log_prints=True)
def re_evaluate_videos(
    topic_id: str,
    video_ids: list[str],
    model_name: str | None = None,
) -> None:
    """
    Re-evaluate selected videos against a topic's current criteria.

    Unlike the main pipeline, this does NOT discover new videos or fetch
    from YouTube. It reads existing video data from the DB and re-runs
    criterion evaluation with upsert (overwriting old results).
    After all evaluations, it cleans up orphaned results from removed criteria.
    """
    logger = get_run_logger()
    logger.info("Re-evaluating %d videos for topic %s", len(video_ids), topic_id)

    topic = get_topic_by_id(topic_id)
    if topic is None:
        logger.error("Topic %s not found", topic_id)
        return

    if not topic.criteria:
        logger.info("No criteria for topic '%s', nothing to evaluate", topic.name)
        # Still clean up stale results (all results are stale if no criteria)
        delete_stale_criterion_results(video_ids, topic_id)
        return

    # Fetch gold standard few-shot examples once for the whole topic
    few_shot_examples = get_gold_standard_video_data(topic_id)
    if few_shot_examples:
        logger.info(
            "Loaded %d gold standard few-shot examples for re-evaluation",
            len(few_shot_examples),
        )

    for video_id in video_ids:
        video_data = get_video_data(video_id)
        if video_data is None:
            logger.warning("Video %s not found in DB, skipping", video_id)
            continue

        for criterion in topic.criteria:
            try:
                result = evaluate_criterion(
                    video=video_data,
                    criterion=criterion,
                    model_name=model_name,
                    few_shot_examples=few_shot_examples,
                )
                save_criterion_result(result)
            except Exception:
                logger.exception(
                    "Failed to evaluate video=%s criterion=%s",
                    video_id,
                    criterion.id,
                )

    # Clean up results from criteria that no longer exist on this topic
    delete_stale_criterion_results(video_ids, topic_id)

    logger.info("Re-evaluation complete for topic '%s'", topic.name)


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    video_pipeline.from_source(
        source=str(Path(__file__).resolve().parent.parent),
        entrypoint="flows/video_pipeline.py:video_pipeline",
    ).serve(name="video-pipeline")
