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
    ClassNodeResultCreate,
    ClassNodeWithRelations,
    FunnelCreator,
    FunnelKeyword,
    FunnelWithRelations,
    GoldStandardWithContext,
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


# ── Internal helpers ──────────────────────────────────────────


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
    funnel_id: str,
) -> list[GoldStandardWithContext]:
    """
    Enrich gold standard records with review content and video descriptions.
    Provides richer context for prompts and few-shot examples without using
    full transcripts (which are too long).
    """
    if not raw_gold_standards:
        return []

    url_to_vid: dict[str, str] = {}
    for gs in raw_gold_standards:
        vid_id = _extract_video_id_from_url(gs["videoUrl"])
        if vid_id:
            url_to_vid[gs["videoUrl"]] = vid_id

    video_ids = list(set(url_to_vid.values()))
    review_map: dict[str, str] = {}
    summary_map: dict[str, str] = {}
    description_map: dict[str, str] = {}

    if video_ids:
        cur.execute(
            """
            SELECT "videoId", content
            FROM "Review"
            WHERE "videoId" = ANY(%s)
              AND "funnelId" = %s
              AND content IS NOT NULL
              AND content != ''
            ORDER BY "updatedAt" DESC
            """,
            (video_ids, funnel_id),
        )
        for row in cur.fetchall():
            if row["videoId"] not in review_map:
                review_map[row["videoId"]] = row["content"]

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


def _load_class_node_gold_standards(
    cur: Any,
    class_node_id: str,
    funnel_id: str,
) -> list[GoldStandardWithContext]:
    """Load and enrich gold standards for a single ClassNode."""
    cur.execute(
        """
        SELECT id, "classNodeId", "videoUrl", title, "isPositive", note,
               "createdAt", "updatedAt"
        FROM "GoldStandard"
        WHERE "classNodeId" = %s
        """,
        (class_node_id,),
    )
    raw_gs = cur.fetchall()
    return _enrich_gold_standards(cur, raw_gs, funnel_id)


def _load_funnel_class_nodes(cur: Any, funnel_id: str) -> list[ClassNodeWithRelations]:
    """
    Load the full ClassNode tree for a funnel (BFS order).
    Returns a flat list; each node has its direct children pre-populated.
    """
    cur.execute(
        """
        SELECT id, description, "parentClassNodeId", "funnelId",
               "createdAt", "updatedAt"
        FROM "ClassNode"
        WHERE "funnelId" = %s
        ORDER BY "createdAt" ASC
        """,
        (funnel_id,),
    )
    rows = cur.fetchall()

    # Index all nodes first
    node_map: dict[str, ClassNodeWithRelations] = {}
    for row in rows:
        gold_standards = _load_class_node_gold_standards(cur, row["id"], funnel_id)
        node_map[row["id"]] = ClassNodeWithRelations(
            **row,
            gold_standards=gold_standards,
        )

    # Attach children
    for node in node_map.values():
        if node.parent_class_node_id and node.parent_class_node_id in node_map:
            node_map[node.parent_class_node_id].children.append(node)

    # BFS order starting from roots (no parentClassNodeId)
    ordered: list[ClassNodeWithRelations] = []
    queue = [n for n in node_map.values() if n.parent_class_node_id is None]
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        queue.extend(current.children)

    return ordered


def _load_funnel_relations(cur: Any, funnel_id: str) -> dict[str, Any]:
    """Load keywords, creators, and ClassNode tree for a funnel."""
    cur.execute(
        """
        SELECT id, "funnelId", keyword, "createdAt", "updatedAt"
        FROM "FunnelKeyword"
        WHERE "funnelId" = %s
        """,
        (funnel_id,),
    )
    keywords = [FunnelKeyword(**kw) for kw in cur.fetchall()]

    cur.execute(
        """
        SELECT id, "funnelId", "channelId", "channelUrl",
               "channelName", "scrapeMonthsBack", "createdAt", "updatedAt"
        FROM "FunnelCreator"
        WHERE "funnelId" = %s
        """,
        (funnel_id,),
    )
    creators = [FunnelCreator(**cr) for cr in cur.fetchall()]

    class_nodes = _load_funnel_class_nodes(cur, funnel_id)

    return dict(keywords=keywords, creators=creators, class_nodes=class_nodes)


# ── Read tasks ────────────────────────────────────────────────


@task(name="get_active_funnels", retries=2, retry_delay_seconds=5)
def get_active_funnels() -> list[FunnelWithRelations]:
    """
    Query all active funnels that are due for processing based on
    pipelineIntervalHours and lastPipelineRunAt.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, "userId", active,
                       "pipelineIntervalHours", "lastPipelineRunAt",
                       "createdAt", "updatedAt"
                FROM "Funnel"
                WHERE active = true
                  AND (
                    "lastPipelineRunAt" IS NULL
                    OR "lastPipelineRunAt" + make_interval(hours => "pipelineIntervalHours")
                       <= NOW()
                  )
                """
            )
            funnel_rows = cur.fetchall()

            funnels: list[FunnelWithRelations] = []
            for row in funnel_rows:
                relations = _load_funnel_relations(cur, row["id"])
                funnels.append(FunnelWithRelations(**row, **relations))

            logger.info("Found %d active funnels due for processing", len(funnels))
            return funnels


@task(name="get_funnel_by_id", retries=2, retry_delay_seconds=5)
def get_funnel_by_id(funnel_id: str) -> FunnelWithRelations | None:
    """
    Fetch a single funnel by ID with all its relations.
    Used for manual trigger (ignores active status and interval).
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, "userId", active,
                       "pipelineIntervalHours", "lastPipelineRunAt",
                       "createdAt", "updatedAt"
                FROM "Funnel" WHERE id = %s
                """,
                (funnel_id,),
            )
            row = cur.fetchone()
            if row is None:
                logger.info("Funnel %s not found", funnel_id)
                return None

            relations = _load_funnel_relations(cur, funnel_id)
            funnel = FunnelWithRelations(**row, **relations)
            logger.info("Fetched funnel '%s' (id=%s)", funnel.name, funnel_id)
            return funnel


@task(name="get_funnel_video_ids", retries=2, retry_delay_seconds=5)
def get_funnel_video_ids(funnel_id: str) -> set[str]:
    """Get all video IDs already linked to a funnel."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT "B" FROM "_FunnelToVideo" WHERE "A" = %s""",
                (funnel_id,),
            )
            ids = {row[0] for row in cur.fetchall()}
            logger.info("Funnel %s has %d linked video(s)", funnel_id, len(ids))
            return ids


@task(name="video_exists")
def video_exists(video_id: str) -> bool:
    """Check if a video already exists in the DB."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM "Video" WHERE id = %s LIMIT 1""",
                (video_id,),
            )
            exists = cur.fetchone() is not None
            logger.info("Video %s exists: %s", video_id, exists)
            return exists


@task(name="class_node_result_exists")
def class_node_result_exists(video_id: str, class_node_id: str) -> bool:
    """Check if a ClassNodeResult already exists for this video+class_node pair."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM "ClassNodeResult"
                WHERE "videoId" = %s AND "classNodeId" = %s LIMIT 1
                """,
                (video_id, class_node_id),
            )
            exists = cur.fetchone() is not None
            logger.info(
                "ClassNodeResult for video=%s class_node=%s exists: %s",
                video_id,
                class_node_id,
                exists,
            )
            return exists


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
                FROM "Video" WHERE id = %s
                """,
                (video_id,),
            )
            row = cur.fetchone()
            if row is None:
                logger.info("Video %s not found in DB", video_id)
                return None

            video = VideoData(
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
            logger.info("Fetched video %s: %s", video_id, video.title)
            return video


@task(name="get_videos_for_funnel", retries=2, retry_delay_seconds=5)
def get_videos_for_funnel(funnel_id: str) -> list[VideoData]:
    """Fetch all VideoData for videos linked to a specific funnel."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT v.id, v.title, v.description, v."channelTitle", v."channelId",
                       v."publishedAt", v."viewCount", v."likeCount", v."commentCount",
                       v."durationSeconds", v.tags, v.transcript, v.summary
                FROM "Video" v
                JOIN "_FunnelToVideo" fv ON fv."B" = v.id
                WHERE fv."A" = %s
                """,
                (funnel_id,),
            )
            rows = cur.fetchall()
            videos = [
                VideoData(
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
                for row in rows
            ]
            logger.info("Fetched %d video(s) for funnel %s", len(videos), funnel_id)
            return videos


@task(name="get_gold_standard_video_data", retries=2, retry_delay_seconds=5)
def get_gold_standard_video_data(
    class_node_id: str,
    funnel_id: str,
    limit: int = 10,
) -> list[tuple[GoldStandardWithContext, VideoData]]:
    """
    Fetch recent gold standards for a ClassNode along with their full VideoData.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, "classNodeId", "videoUrl", title, "isPositive", note,
                       "createdAt", "updatedAt"
                FROM "GoldStandard"
                WHERE "classNodeId" = %s ORDER BY "createdAt" DESC LIMIT %s
                """,
                (class_node_id, limit),
            )
            gs_rows = cur.fetchall()
            if not gs_rows:
                return []

            url_to_vid: dict[str, str] = {}
            for gs in gs_rows:
                vid_id = _extract_video_id_from_url(gs["videoUrl"])
                if vid_id:
                    url_to_vid[gs["videoUrl"]] = vid_id

            video_ids = list(set(url_to_vid.values()))
            if not video_ids:
                return []

            enriched_gs = _enrich_gold_standards(cur, gs_rows, funnel_id)

            cur.execute(
                """
                SELECT id, title, description, "channelTitle", "channelId",
                       "publishedAt", "viewCount", "likeCount", "commentCount",
                       "durationSeconds", tags, summary
                FROM "Video" WHERE id = ANY(%s)
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

            results: list[tuple[GoldStandardWithContext, VideoData]] = []
            for gs in enriched_gs:
                vid_id = url_to_vid.get(gs.video_url)
                if vid_id and vid_id in video_map:
                    results.append((gs, video_map[vid_id]))

            logger.info(
                "Fetched %d gold standard video examples for class_node %s",
                len(results),
                class_node_id,
            )
            return results


@task(name="get_class_node_video_ids", retries=2, retry_delay_seconds=5)
def get_class_node_video_ids(class_node_id: str) -> set[str]:
    """Get all video IDs that have a ClassNodeResult for a given ClassNode."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT "videoId" FROM "ClassNodeResult" WHERE "classNodeId" = %s""",
                (class_node_id,),
            )
            ids = {row[0] for row in cur.fetchall()}
            logger.info(
                "ClassNode %s has %d evaluated video(s)", class_node_id, len(ids)
            )
            return ids


@task(name="delete_stale_class_node_results", retries=2, retry_delay_seconds=5)
def delete_stale_class_node_results(video_ids: list[str], funnel_id: str) -> int:
    """Delete ClassNodeResult rows where the ClassNode no longer belongs to the funnel."""
    if not video_ids:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM "ClassNodeResult"
                WHERE "videoId" = ANY(%s)
                  AND "classNodeId" NOT IN (
                      SELECT id FROM "ClassNode" WHERE "funnelId" = %s
                  )
                """,
                (video_ids, funnel_id),
            )
            deleted = cur.rowcount
            conn.commit()
    logger.info(
        "Deleted %d stale ClassNodeResults for %d videos in funnel %s",
        deleted,
        len(video_ids),
        funnel_id,
    )
    return deleted


# ── Write tasks ───────────────────────────────────────────────


def _generate_cuid() -> str:
    """Generate a CUID-like ID."""
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
            if video.channel_id:
                cur.execute(
                    """
                    INSERT INTO "Channel" (id, title, "createdAt", "updatedAt")
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title, "updatedAt" = EXCLUDED."updatedAt"
                    """,
                    (video.channel_id, video.channel_title, now, now),
                )

            cur.execute(
                """
                INSERT INTO "Video" (
                    id, title, description, "channelTitle", "channelId",
                    "publishedAt", "viewCount", "likeCount", "commentCount",
                    "durationSeconds", tags, transcript, summary,
                    "createdAt", "updatedAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


@task(name="link_video_to_funnel", retries=2, retry_delay_seconds=5)
def link_video_to_funnel(video_id: str, funnel_id: str) -> None:
    """Link a video to a funnel via the _FunnelToVideo junction table."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "_FunnelToVideo" ("A", "B") VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (funnel_id, video_id),
            )
            conn.commit()
    logger.info("Linked video %s to funnel %s", video_id, funnel_id)


@task(name="save_class_node_result", retries=2, retry_delay_seconds=5)
def save_class_node_result(result: ClassNodeResultCreate) -> None:
    """Insert or update a ClassNodeResult."""
    now = datetime.now(timezone.utc)
    result_id = _generate_cuid()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "ClassNodeResult" (
                    id, "videoId", "classNodeId", result, explanation,
                    "modelUsed", "createdAt", "updatedAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("videoId", "classNodeId") DO UPDATE SET
                    result = EXCLUDED.result,
                    explanation = EXCLUDED.explanation,
                    "modelUsed" = EXCLUDED."modelUsed",
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                (
                    result_id,
                    result.video_id,
                    result.class_node_id,
                    result.result.value,
                    result.explanation,
                    result.model_used,
                    now,
                    now,
                ),
            )
            conn.commit()
    logger.info(
        "Saved ClassNodeResult: video=%s class_node=%s result=%s",
        result.video_id,
        result.class_node_id,
        result.result.value,
    )


@task(name="update_funnel_last_run", retries=2, retry_delay_seconds=5)
def update_funnel_last_run(funnel_id: str) -> None:
    """Set lastPipelineRunAt to now for a funnel."""
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE "Funnel" SET "lastPipelineRunAt" = %s, "updatedAt" = %s WHERE id = %s
                """,
                (now, now, funnel_id),
            )
            conn.commit()
    logger.info("Updated lastPipelineRunAt for funnel %s", funnel_id)
