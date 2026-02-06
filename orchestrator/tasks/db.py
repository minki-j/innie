"""
Database tasks for the orchestrator pipeline.

Uses psycopg2 with raw SQL against the Prisma-managed Postgres schema.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import psycopg2
import psycopg2.extras
from prefect import task

from config import DATABASE_URL
from models.schemas import (
    Criterion,
    CriterionResultCreate,
    GoldStandard,
    GoldStandardWithContext,
    Topic,
    TopicCreator,
    TopicKeyword,
    VideoData,
)

logger = logging.getLogger(__name__)


# ── Connection helper ─────────────────────────────────────────


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Get a psycopg2 connection using the configured DATABASE_URL."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


# ── Read tasks ────────────────────────────────────────────────


_YT_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
    r"([a-zA-Z0-9_-]{11})"
)


def _extract_video_id_from_url(url: str) -> str | None:
    """Extract a YouTube video ID from a URL."""
    match = _YT_VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def _enrich_gold_standards(
    cur: Any,
    raw_gold_standards: list[dict],
    topic_id: str,
) -> list[GoldStandardWithContext]:
    """
    Enrich gold standard records with review content and video descriptions.
    This provides richer context for AGI search prompts without using
    full transcripts (which are too long).
    """
    if not raw_gold_standards:
        return []

    # Extract video IDs from gold standard URLs
    url_to_vid: dict[str, str] = {}
    for gs in raw_gold_standards:
        vid_id = _extract_video_id_from_url(gs["videoUrl"])
        if vid_id:
            url_to_vid[gs["videoUrl"]] = vid_id

    video_ids = list(set(url_to_vid.values()))
    review_map: dict[str, str] = {}  # video_id -> review content
    summary_map: dict[str, str] = {}  # video_id -> LLM-generated summary
    description_map: dict[str, str] = {}  # video_id -> YouTube description (fallback)

    if video_ids:
        # Fetch review content for these videos under this topic
        cur.execute(
            """
            SELECT "videoId", content
            FROM "Review"
            WHERE "videoId" = ANY(%s)
              AND "topicId" = %s
              AND content IS NOT NULL
              AND content != ''
            ORDER BY "updatedAt" DESC
            """,
            (video_ids, topic_id),
        )
        for row in cur.fetchall():
            # Keep only the most recent review per video (already ordered DESC)
            if row["videoId"] not in review_map:
                review_map[row["videoId"]] = row["content"]

        # Fetch video summary and description
        cur.execute(
            """
            SELECT id, summary, description
            FROM "Video"
            WHERE id = ANY(%s)
            """,
            (video_ids,),
        )
        for row in cur.fetchall():
            if row["summary"]:
                summary_map[row["id"]] = row["summary"]
            if row["description"]:
                description_map[row["id"]] = row["description"]

    # Build enriched gold standards
    enriched: list[GoldStandardWithContext] = []
    for gs in raw_gold_standards:
        vid_id = url_to_vid.get(gs["videoUrl"])
        enriched.append(
            GoldStandardWithContext(
                **gs,
                review_content=review_map.get(vid_id) if vid_id else None,
                video_summary=summary_map.get(vid_id) if vid_id else None,
                video_description=description_map.get(vid_id) if vid_id else None,
            )
        )

    return enriched


def _load_topic_relations(cur: Any, topic_id: str) -> dict[str, list]:
    """Load keywords, creators, criteria, and gold standards for a topic."""
    # Fetch keywords
    cur.execute(
        """
        SELECT id, "topicId", keyword
        FROM "TopicKeyword"
        WHERE "topicId" = %s
        """,
        (topic_id,),
    )
    keywords = [TopicKeyword(**kw) for kw in cur.fetchall()]

    # Fetch creators
    cur.execute(
        """
        SELECT id, "topicId", "channelId", "channelUrl",
               "channelName", "scrapeMonthsBack"
        FROM "TopicCreator"
        WHERE "topicId" = %s
        """,
        (topic_id,),
    )
    creators = [TopicCreator(**cr) for cr in cur.fetchall()]

    # Fetch criteria
    cur.execute(
        """
        SELECT id, "topicId", condition, include, level, "order"
        FROM "Criterion"
        WHERE "topicId" = %s
        ORDER BY "order" ASC
        """,
        (topic_id,),
    )
    criteria = [Criterion(**c) for c in cur.fetchall()]

    # Fetch gold standards
    cur.execute(
        """
        SELECT id, "topicId", "videoUrl", title, "isPositive", note
        FROM "GoldStandard"
        WHERE "topicId" = %s
        """,
        (topic_id,),
    )
    raw_gold_standards = cur.fetchall()

    # Enrich gold standards with review content and video descriptions
    gold_standards = _enrich_gold_standards(cur, raw_gold_standards, topic_id)

    return dict(
        keywords=keywords,
        creators=creators,
        criteria=criteria,
        gold_standards=gold_standards,
    )


@task(name="get_active_topics", retries=2, retry_delay_seconds=5)
def get_active_topics() -> list[Topic]:
    """
    Query all active topics that are due for processing, based on
    their pipelineIntervalHours and lastPipelineRunAt.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch active topics that are due for a run:
            # - lastPipelineRunAt is NULL (never run), OR
            # - enough time has elapsed since last run
            cur.execute(
                """
                SELECT id, name, description, "userId", active,
                       "pipelineIntervalHours", "lastPipelineRunAt"
                FROM "Topic"
                WHERE active = true
                  AND (
                    "lastPipelineRunAt" IS NULL
                    OR "lastPipelineRunAt" + make_interval(hours => "pipelineIntervalHours")
                       <= NOW()
                  )
                """
            )
            topic_rows = cur.fetchall()

            topics: list[Topic] = []
            for row in topic_rows:
                relations = _load_topic_relations(cur, row["id"])
                topics.append(Topic(**row, **relations))

            return topics


@task(name="get_topic_by_id", retries=2, retry_delay_seconds=5)
def get_topic_by_id(topic_id: str) -> Topic | None:
    """
    Fetch a single topic by ID with all its relations.
    Used for manual trigger (ignores active status and interval).
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, "userId", active,
                       "pipelineIntervalHours", "lastPipelineRunAt"
                FROM "Topic"
                WHERE id = %s
                """,
                (topic_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            relations = _load_topic_relations(cur, topic_id)
            return Topic(**row, **relations)


@task(name="update_topic_last_run", retries=2, retry_delay_seconds=5)
def update_topic_last_run(topic_id: str) -> None:
    """Set lastPipelineRunAt to now for a topic."""
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE "Topic"
                SET "lastPipelineRunAt" = %s, "updatedAt" = %s
                WHERE id = %s
                """,
                (now, now, topic_id),
            )
            conn.commit()
    logger.info("Updated lastPipelineRunAt for topic %s", topic_id)


@task(name="get_topic_video_ids", retries=2, retry_delay_seconds=5)
def get_topic_video_ids(topic_id: str) -> set[str]:
    """Get all video IDs already linked to a topic."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "B" FROM "_TopicToVideo" WHERE "A" = %s
                """,
                (topic_id,),
            )
            return {row[0] for row in cur.fetchall()}


@task(name="video_exists")
def video_exists(video_id: str) -> bool:
    """Check if a video already exists in the DB."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM "Video" WHERE id = %s LIMIT 1""",
                (video_id,),
            )
            return cur.fetchone() is not None


@task(name="criterion_result_exists")
def criterion_result_exists(video_id: str, criterion_id: str) -> bool:
    """Check if a criterion result already exists for this video+criterion pair."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM "CriterionResult"
                WHERE "videoId" = %s AND "criterionId" = %s
                LIMIT 1
                """,
                (video_id, criterion_id),
            )
            return cur.fetchone() is not None


@task(name="get_video_data", retries=2, retry_delay_seconds=5)
def get_video_data(video_id: str) -> VideoData | None:
    """Fetch a VideoData from the DB (metadata + transcript) for re-evaluation."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, description, "channelTitle", "channelId",
                       "publishedAt", "viewCount", "likeCount", "commentCount",
                       "durationSeconds", tags, transcript, summary
                FROM "Video"
                WHERE id = %s
                """,
                (video_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            return VideoData(
                video_id=row["id"],
                title=row["title"] or "",
                description=row["description"] or "",
                channel_title=row["channelTitle"] or "",
                channel_id=row["channelId"] or "",
                published_at=row["publishedAt"],
                view_count=row["viewCount"] or 0,
                like_count=row["likeCount"] or 0,
                comment_count=row["commentCount"] or 0,
                duration_seconds=row["durationSeconds"] or 0,
                tags=row["tags"] or [],
                transcript=row["transcript"],
                summary=row["summary"],
            )


@task(name="get_gold_standard_video_data", retries=2, retry_delay_seconds=5)
def get_gold_standard_video_data(
    topic_id: str,
    limit: int = 10,
) -> list[tuple[GoldStandardWithContext, VideoData]]:
    """
    Fetch recent gold standards for a topic along with their full VideoData.

    Returns a list of (GoldStandardWithContext, VideoData) pairs.
    Only gold standards that have a matching Video row are included.
    Transcript is excluded (set to None) — callers use summary instead.
    Ordered by most recently created, limited to `limit` entries.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch gold standards ordered by most recent
            cur.execute(
                """
                SELECT id, "topicId", "videoUrl", title, "isPositive", note,
                       "createdAt", "updatedAt"
                FROM "GoldStandard"
                WHERE "topicId" = %s
                ORDER BY "createdAt" DESC
                LIMIT %s
                """,
                (topic_id, limit),
            )
            gs_rows = cur.fetchall()
            if not gs_rows:
                return []

            # Map gold standard URL -> video ID
            url_to_vid: dict[str, str] = {}
            for gs in gs_rows:
                vid_id = _extract_video_id_from_url(gs["videoUrl"])
                if vid_id:
                    url_to_vid[gs["videoUrl"]] = vid_id

            video_ids = list(set(url_to_vid.values()))
            if not video_ids:
                return []

            # Enrich gold standards (adds review_content, video_summary, video_description)
            enriched_gs = _enrich_gold_standards(cur, gs_rows, topic_id)

            # Fetch full video data for gold standard videos (without transcript)
            cur.execute(
                """
                SELECT id, title, description, "channelTitle", "channelId",
                       "publishedAt", "viewCount", "likeCount", "commentCount",
                       "durationSeconds", tags, summary
                FROM "Video"
                WHERE id = ANY(%s)
                """,
                (video_ids,),
            )
            video_map: dict[str, VideoData] = {}
            for row in cur.fetchall():
                video_map[row["id"]] = VideoData(
                    video_id=row["id"],
                    title=row["title"] or "",
                    description=row["description"] or "",
                    channel_title=row["channelTitle"] or "",
                    channel_id=row["channelId"] or "",
                    published_at=row["publishedAt"],
                    view_count=row["viewCount"] or 0,
                    like_count=row["likeCount"] or 0,
                    comment_count=row["commentCount"] or 0,
                    duration_seconds=row["durationSeconds"] or 0,
                    tags=row["tags"] or [],
                    transcript=None,  # omit transcript to save tokens
                    summary=row["summary"],
                )

            # Pair enriched gold standards with their video data
            results: list[tuple[GoldStandardWithContext, VideoData]] = []
            for gs in enriched_gs:
                vid_id = url_to_vid.get(gs.video_url)
                if vid_id and vid_id in video_map:
                    results.append((gs, video_map[vid_id]))

            logger.info(
                "Fetched %d gold standard video examples for topic %s",
                len(results),
                topic_id,
            )
            return results


@task(name="delete_stale_criterion_results", retries=2, retry_delay_seconds=5)
def delete_stale_criterion_results(video_ids: list[str], topic_id: str) -> int:
    """
    Delete orphaned CriterionResult rows for the given videos where the
    criterionId no longer exists in the Criterion table (i.e. the criterion
    was deleted). Call AFTER new evaluations have been upserted.

    Note: Prisma CASCADE should handle most of these, but this is a safety net.
    """
    if not video_ids:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM "CriterionResult"
                WHERE "videoId" = ANY(%s)
                  AND "criterionId" NOT IN (
                      SELECT id FROM "Criterion" WHERE "topicId" = %s
                  )
                """,
                (video_ids, topic_id),
            )
            deleted = cur.rowcount
            conn.commit()
    logger.info(
        "Deleted %d stale criterion results for %d videos in topic %s",
        deleted,
        len(video_ids),
        topic_id,
    )
    return deleted


# ── Write tasks ───────────────────────────────────────────────


def _generate_cuid() -> str:
    """Generate a CUID-like ID. Uses cuid2-style random ID."""
    import hashlib
    import os
    import time

    raw = f"{time.time_ns()}-{os.urandom(16).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:25]


@task(name="save_video", retries=2, retry_delay_seconds=5)
def save_video(video: VideoData) -> None:
    """Upsert a video and its channel into the DB."""
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Upsert channel (if we have channel info)
            if video.channel_id:
                cur.execute(
                    """
                    INSERT INTO "Channel" (id, title, "createdAt", "updatedAt")
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        "updatedAt" = EXCLUDED."updatedAt"
                    """,
                    (video.channel_id, video.channel_title, now, now),
                )

            # Upsert video
            cur.execute(
                """
                INSERT INTO "Video" (
                    id, title, description, "channelTitle", "channelId",
                    "publishedAt", "viewCount", "likeCount", "commentCount",
                    "durationSeconds", tags, transcript, summary,
                    "createdAt", "updatedAt"
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    "channelTitle" = EXCLUDED."channelTitle",
                    "viewCount" = EXCLUDED."viewCount",
                    "likeCount" = EXCLUDED."likeCount",
                    "commentCount" = EXCLUDED."commentCount",
                    transcript = COALESCE(EXCLUDED.transcript, "Video".transcript),
                    summary = COALESCE(EXCLUDED.summary, "Video".summary),
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                (
                    video.video_id,
                    video.title,
                    video.description,
                    video.channel_title,
                    video.channel_id,
                    video.published_at or now,
                    video.view_count,
                    video.like_count,
                    video.comment_count,
                    video.duration_seconds,
                    video.tags,
                    video.transcript,
                    video.summary,
                    now,
                    now,
                ),
            )

            conn.commit()
    logger.info("Saved video %s: %s", video.video_id, video.title)


@task(name="link_video_to_topic", retries=2, retry_delay_seconds=5)
def link_video_to_topic(video_id: str, topic_id: str) -> None:
    """Link a video to a topic via the _TopicToVideo junction table."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "_TopicToVideo" ("A", "B")
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (topic_id, video_id),
            )
            conn.commit()
    logger.info("Linked video %s to topic %s", video_id, topic_id)


@task(name="save_criterion_result", retries=2, retry_delay_seconds=5)
def save_criterion_result(result: CriterionResultCreate) -> None:
    """Insert or update a criterion result."""
    now = datetime.now(timezone.utc)
    result_id = _generate_cuid()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "CriterionResult" (
                    id, "videoId", "criterionId", result, explanation,
                    "modelUsed", "createdAt", "updatedAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("videoId", "criterionId") DO UPDATE SET
                    result = EXCLUDED.result,
                    explanation = EXCLUDED.explanation,
                    "modelUsed" = EXCLUDED."modelUsed",
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                (
                    result_id,
                    result.video_id,
                    result.criterion_id,
                    result.result.value,
                    result.explanation,
                    result.model_used,
                    now,
                    now,
                ),
            )
            conn.commit()
    logger.info(
        "Saved criterion result: video=%s criterion=%s result=%s",
        result.video_id,
        result.criterion_id,
        result.result.value,
    )
