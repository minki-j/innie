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
    ClassNodeModelVerdictCreate,
    ClassNodeResultCreate,
    ClassNodeWithRelations,
    FunnelCreator,
    FunnelKeyword,
    FunnelWithRelations,
    GoldStandardWithContext,
    IdeaGraphGenerationStatus,
    IdeaGraphSnapshot,
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
        SELECT id, title, description, "parentClassNodeId", "funnelId",
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


@task(name="get_funnels_due_for_pipeline", retries=2, retry_delay_seconds=5)
def get_funnels_due_for_pipeline() -> list[FunnelWithRelations]:
    """
    Active funnels whose pipeline interval has elapsed (or never ran), using
    pipelineIntervalHours and lastPipelineRunAt.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, "userId", active,
                       "pipelineIntervalHours", "lastPipelineRunAt",
                       "maxVideosPerKeyword", "maxVideosPerCreator",
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

            logger.info("Found %d funnels due for pipeline run", len(funnels))
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
                       "maxVideosPerKeyword", "maxVideosPerCreator",
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
                """SELECT "videoId" FROM "FunnelVideo" WHERE "funnelId" = %s""",
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
    """Link a video to a funnel and mark it as COMPLETED in FunnelVideo."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "FunnelVideo" ("funnelId", "videoId", "status", "createdAt", "updatedAt")
                VALUES (%s, %s, 'COMPLETED', NOW(), NOW())
                ON CONFLICT ("funnelId", "videoId") DO UPDATE
                    SET "status" = 'COMPLETED', "updatedAt" = NOW()
                """,
                (funnel_id, video_id),
            )
            conn.commit()
    logger.info("Linked video %s to funnel %s", video_id, funnel_id)


@task(name="save_class_node_result", retries=2, retry_delay_seconds=5)
def save_class_node_result(result: ClassNodeResultCreate) -> str:
    """Insert or update a ClassNodeResult. Returns the row id."""
    now = datetime.now(timezone.utc)
    result_id = _generate_cuid()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "ClassNodeResult" (
                    id, "videoId", "classNodeId", result, confidence, explanation,
                    "createdAt", "updatedAt"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("videoId", "classNodeId") DO UPDATE SET
                    result = EXCLUDED.result,
                    confidence = EXCLUDED.confidence,
                    explanation = EXCLUDED.explanation,
                    "updatedAt" = EXCLUDED."updatedAt"
                RETURNING id
                """,
                (
                    result_id,
                    result.video_id,
                    result.class_node_id,
                    result.result.value,
                    result.confidence_score,
                    result.explanation,
                    now,
                    now,
                ),
            )
            returned_id = cur.fetchone()[0]
            conn.commit()
    logger.info(
        "Saved ClassNodeResult: video=%s class_node=%s result=%s",
        result.video_id,
        result.class_node_id,
        result.result.value,
    )
    return returned_id


@task(name="bulk_check_existing_class_node_results", retries=2, retry_delay_seconds=5)
def bulk_check_existing_class_node_results(
    pairs: list[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Return the subset of (video_id, class_node_id) pairs that already exist in the DB."""
    if not pairs:
        return set()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "videoId", "classNodeId"
                FROM "ClassNodeResult"
                WHERE ("videoId", "classNodeId") = ANY(%s)
                """,
                (list(pairs),),
            )
            existing = {(row[0], row[1]) for row in cur.fetchall()}
    logger.info(
        "bulk_check_existing_class_node_results: %d/%d pairs already exist",
        len(existing),
        len(pairs),
    )
    return existing


@task(name="bulk_save_class_node_results", retries=2, retry_delay_seconds=5)
def bulk_save_class_node_results(
    results: list[ClassNodeResultCreate],
) -> dict[tuple[str, str], str]:
    """
    Batch-upsert ClassNodeResult rows.

    Returns a mapping of (video_id, class_node_id) -> result_id so callers can
    immediately build the associated ClassNodeModelVerdict rows.
    """
    if not results:
        return {}
    now = datetime.now(timezone.utc)
    rows = [
        (
            _generate_cuid(),
            r.video_id,
            r.class_node_id,
            r.result.value,
            r.confidence_score,
            r.explanation,
            now,
            now,
        )
        for r in results
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            returned = psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO "ClassNodeResult" (
                    id, "videoId", "classNodeId", result, confidence, explanation,
                    "createdAt", "updatedAt"
                ) VALUES %s
                ON CONFLICT ("videoId", "classNodeId") DO UPDATE SET
                    result = EXCLUDED.result,
                    confidence = EXCLUDED.confidence,
                    explanation = EXCLUDED.explanation,
                    "updatedAt" = EXCLUDED."updatedAt"
                RETURNING id, "videoId", "classNodeId"
                """,
                rows,
                fetch=True,
            )
            conn.commit()
    result_id_map = {(row[1], row[2]): row[0] for row in returned}
    logger.info("bulk_save_class_node_results: upserted %d ClassNodeResult rows", len(result_id_map))
    return result_id_map


@task(name="ensure_llms_exist", retries=2, retry_delay_seconds=5)
def ensure_llms_exist(llm_ids: list[str]) -> None:
    """Upsert LLM rows for all model IDs, deriving provider from the model name."""
    if not llm_ids:
        return
    now = datetime.now(timezone.utc)
    rows = [
        (
            llm_id,
            "anthropic" if "claude" in llm_id.lower() else "openai",
            now,
            now,
        )
        for llm_id in llm_ids
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO "LLM" (id, provider, "createdAt", "updatedAt")
                VALUES %s
                ON CONFLICT (id) DO NOTHING
                """,
                rows,
            )
            conn.commit()
    logger.info("Ensured %d LLM row(s): %s", len(llm_ids), llm_ids)


@task(name="save_class_node_model_verdicts", retries=2, retry_delay_seconds=5)
def save_class_node_model_verdicts(verdicts: list[ClassNodeModelVerdictCreate]) -> None:
    """Batch-insert ClassNodeModelVerdict rows."""
    if not verdicts:
        return
    now = datetime.now(timezone.utc)
    rows = [
        (
            _generate_cuid(),
            v.video_id,
            v.class_node_id,
            v.class_node_result_id,
            v.llm_id,
            v.rationale,
            v.verdict,
            now,
            now,
        )
        for v in verdicts
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO "ClassNodeModelVerdict" (
                    id, "videoId", "classNodeId", "classNodeResultId",
                    "llmId", rationale, verdict, "createdAt", "updatedAt"
                ) VALUES %s
                ON CONFLICT ("videoId", "classNodeId", "llmId") DO UPDATE SET
                    rationale = EXCLUDED.rationale,
                    verdict = EXCLUDED.verdict,
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                rows,
            )
            conn.commit()
    logger.info("Saved %d ClassNodeModelVerdict rows", len(verdicts))


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


def get_video_for_idea_graph(video_id: str) -> dict[str, str] | None:
    """Return the video title and transcript needed for idea graph generation."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, transcript
                FROM "Video"
                WHERE id = %s
                LIMIT 1
                """,
                (video_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "title": row["title"],
                "transcript": row["transcript"],
            }


def get_idea_graph_snapshot(user_id: str, video_id: str) -> IdeaGraphSnapshot:
    """Load the current graph snapshot for a user/video pair."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id
                FROM "IdeaGraph"
                WHERE "userId" = %s AND "videoId" = %s
                LIMIT 1
                """,
                (user_id, video_id),
            )
            graph = cur.fetchone()
            if not graph:
                return IdeaGraphSnapshot()

            graph_id = graph["id"]

            cur.execute(
                """
                SELECT id, type, title, content, x, y, collapsed
                FROM "IdeaGraphNode"
                WHERE "graphId" = %s
                ORDER BY "createdAt" ASC
                """,
                (graph_id,),
            )
            node_rows = cur.fetchall()

            cur.execute(
                """
                SELECT id, "sourceNodeId", "targetNodeId", type, label
                FROM "IdeaGraphEdge"
                WHERE "graphId" = %s
                ORDER BY "createdAt" ASC
                """,
                (graph_id,),
            )
            edge_rows = cur.fetchall()

            cur.execute(
                """
                SELECT s.id, s."nodeId", s.paraphrase, s.quote, s."startSec", s."endSec"
                FROM "IdeaGraphNodeSource" s
                JOIN "IdeaGraphNode" n ON n.id = s."nodeId"
                WHERE n."graphId" = %s
                ORDER BY s."startSec" ASC, s."createdAt" ASC
                """,
                (graph_id,),
            )
            source_rows = cur.fetchall()

    sources_by_node: dict[str, list[dict[str, Any]]] = {}
    for row in source_rows:
        sources_by_node.setdefault(row["nodeId"], []).append(
            {
                "id": row["id"],
                "paraphrase": row["paraphrase"],
                "quote": row["quote"],
                "start_sec": float(row["startSec"]),
                "end_sec": float(row["endSec"]),
            }
        )

    return IdeaGraphSnapshot(
        nodes=[
            {
                "id": row["id"],
                "type": row["type"],
                "title": row["title"],
                "content": row["content"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "collapsed": row["collapsed"],
                "transcript_sources": sources_by_node.get(row["id"], []),
            }
            for row in node_rows
        ],
        edges=[
            {
                "id": row["id"],
                "source_node_id": row["sourceNodeId"],
                "target_node_id": row["targetNodeId"],
                "type": row["type"],
                "label": row["label"],
            }
            for row in edge_rows
        ],
    )


def set_idea_graph_generation_status(
    user_id: str,
    video_id: str,
    status: IdeaGraphGenerationStatus,
    error: str | None = None,
) -> None:
    """Upsert generation status for an idea graph."""
    now = datetime.now(timezone.utc)
    generated_at = now if status == IdeaGraphGenerationStatus.COMPLETED else None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "IdeaGraph" (
                    id, "userId", "videoId", "generationStatus", "generationError",
                    "generatedAt", "createdAt", "updatedAt"
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("userId", "videoId") DO UPDATE SET
                    "generationStatus" = EXCLUDED."generationStatus",
                    "generationError" = EXCLUDED."generationError",
                    "generatedAt" = EXCLUDED."generatedAt",
                    "updatedAt" = EXCLUDED."updatedAt"
                """,
                (
                    _generate_cuid(),
                    user_id,
                    video_id,
                    status.value,
                    error,
                    generated_at,
                    now,
                    now,
                ),
            )
            conn.commit()


def replace_idea_graph(user_id: str, video_id: str, snapshot: IdeaGraphSnapshot) -> None:
    """Replace an idea graph atomically for a user/video pair."""
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "IdeaGraph" (
                    id, "userId", "videoId", "generationStatus", "generatedAt",
                    "createdAt", "updatedAt"
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("userId", "videoId") DO UPDATE SET
                    "generationStatus" = EXCLUDED."generationStatus",
                    "generationError" = NULL,
                    "generatedAt" = EXCLUDED."generatedAt",
                    "updatedAt" = EXCLUDED."updatedAt"
                RETURNING id
                """,
                (
                    _generate_cuid(),
                    user_id,
                    video_id,
                    IdeaGraphGenerationStatus.COMPLETED.value,
                    now,
                    now,
                    now,
                ),
            )
            graph_id = cur.fetchone()[0]

            cur.execute("""DELETE FROM "IdeaGraphEdge" WHERE "graphId" = %s""", (graph_id,))
            cur.execute("""DELETE FROM "IdeaGraphNode" WHERE "graphId" = %s""", (graph_id,))

            if snapshot.nodes:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO "IdeaGraphNode" (
                        id, "graphId", type, title, content, x, y, collapsed,
                        "createdAt", "updatedAt"
                    ) VALUES %s
                    """,
                    [
                        (
                            node.id,
                            graph_id,
                            node.type.value,
                            node.title,
                            node.content,
                            node.x,
                            node.y,
                            node.collapsed,
                            now,
                            now,
                        )
                        for node in snapshot.nodes
                    ],
                )

                source_rows = [
                    (
                        source.id,
                        node.id,
                        source.paraphrase,
                        source.quote,
                        source.start_sec,
                        source.end_sec,
                        now,
                        now,
                    )
                    for node in snapshot.nodes
                    for source in node.transcript_sources
                ]
                if source_rows:
                    psycopg2.extras.execute_values(
                        cur,
                        """
                        INSERT INTO "IdeaGraphNodeSource" (
                            id, "nodeId", paraphrase, quote, "startSec", "endSec",
                            "createdAt", "updatedAt"
                        ) VALUES %s
                        """,
                        source_rows,
                    )

            if snapshot.edges:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO "IdeaGraphEdge" (
                        id, "graphId", "sourceNodeId", "targetNodeId", type, label,
                        "createdAt", "updatedAt"
                    ) VALUES %s
                    """,
                    [
                        (
                            edge.id,
                            graph_id,
                            edge.source_node_id,
                            edge.target_node_id,
                            edge.type.value,
                            edge.label,
                            now,
                            now,
                        )
                        for edge in snapshot.edges
                    ],
                )

            conn.commit()
