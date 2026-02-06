"""
Database access layer for the lab server.

Uses psycopg2 with raw SQL against the Prisma-managed Postgres schema.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import psycopg2
import psycopg2.extras

from server.config import DATABASE_URL
from server.models import (
    TrainingDatapoint,
    TrainingMethod,
    TrainingRunResponse,
    TrainingStatus,
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


def _generate_cuid() -> str:
    """Generate a CUID-like ID."""
    raw = f"{time.time_ns()}-{os.urandom(16).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:25]


# ── Training data queries ────────────────────────────────────


def get_training_data(user_id: str, topic_id: str) -> list[TrainingDatapoint]:
    """
    Fetch all reviews for a user+topic, joined with video transcripts
    and topic metadata, to build training datapoints.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    r."videoId",
                    v.title AS video_title,
                    v.transcript,
                    r.rating,
                    r.content,
                    t.name AS topic_name,
                    t.description AS topic_description
                FROM "Review" r
                JOIN "Video" v ON v.id = r."videoId"
                JOIN "Topic" t ON t.id = r."topicId"
                WHERE r."userId" = %s
                  AND r."topicId" = %s
                  AND v.transcript IS NOT NULL
                  AND v.transcript != ''
                """,
                (user_id, topic_id),
            )
            rows = cur.fetchall()

    datapoints: list[TrainingDatapoint] = []
    for row in rows:
        # Parse the JSON content field
        content: dict[str, Any] = {}
        if row["content"]:
            try:
                content = json.loads(row["content"])
            except (json.JSONDecodeError, TypeError):
                content = {}

        feedback = content.get("feedback", "")
        if not feedback:
            continue  # skip reviews without feedback text

        like_aspects = content.get("likeAspects", [])

        datapoints.append(
            TrainingDatapoint(
                video_id=row["videoId"],
                video_title=row["video_title"] or "",
                transcript=row["transcript"] or "",
                rating=row["rating"],
                feedback=feedback,
                like_aspects=like_aspects if isinstance(like_aspects, list) else [],
                topic_name=row["topic_name"] or "",
                topic_description=row["topic_description"] or "",
            )
        )

    return datapoints


def user_and_topic_exist(user_id: str, topic_id: str) -> bool:
    """Check that the user owns the topic."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM "Topic"
                WHERE id = %s AND "userId" = %s
                LIMIT 1
                """,
                (topic_id, user_id),
            )
            return cur.fetchone() is not None


# ── Training run CRUD ────────────────────────────────────────


def get_next_version(user_id: str, topic_id: str, method: TrainingMethod) -> int:
    """Get the next version number for a (userId, topicId, method) combo."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM "TrainingRun"
                WHERE "userId" = %s AND "topicId" = %s AND method = %s
                """,
                (user_id, topic_id, method.value),
            )
            result = cur.fetchone()
            return result[0] if result else 1


def create_training_run(
    *,
    user_id: str,
    topic_id: str,
    method: TrainingMethod,
    model_name: str,
    version: int,
    base_model: str,
    config: dict[str, Any] | None = None,
    webhook_url: str | None = None,
    dataset_size: int | None = None,
) -> str:
    """Create a new TrainingRun record. Returns the generated ID."""
    run_id = _generate_cuid()
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "TrainingRun" (
                    id, "userId", "topicId", status, method, "modelName",
                    version, "baseModel", config, "webhookUrl", "datasetSize",
                    "isActive", "createdAt", "updatedAt"
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    run_id,
                    user_id,
                    topic_id,
                    TrainingStatus.PENDING.value,
                    method.value,
                    model_name,
                    version,
                    base_model,
                    json.dumps(config) if config else None,
                    webhook_url,
                    dataset_size,
                    False,
                    now,
                    now,
                ),
            )
            conn.commit()

    logger.info("Created training run %s: %s", run_id, model_name)
    return run_id


def update_training_run_status(
    run_id: str,
    status: TrainingStatus,
    *,
    checkpoint_path: str | None = None,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
    dataset_size: int | None = None,
) -> None:
    """Update the status of a training run."""
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            updates = ['"status" = %s', '"updatedAt" = %s']
            params: list[Any] = [status.value, now]

            if checkpoint_path is not None:
                updates.append('"checkpointPath" = %s')
                params.append(checkpoint_path)

            if metrics is not None:
                updates.append("metrics = %s")
                params.append(json.dumps(metrics))

            if error is not None:
                updates.append("error = %s")
                params.append(error)

            if dataset_size is not None:
                updates.append('"datasetSize" = %s')
                params.append(dataset_size)

            if status == TrainingStatus.COMPLETED:
                updates.append('"completedAt" = %s')
                params.append(now)

            params.append(run_id)
            cur.execute(
                f'UPDATE "TrainingRun" SET {", ".join(updates)} WHERE id = %s',
                params,
            )
            conn.commit()

    logger.info("Updated training run %s -> %s", run_id, status.value)


def mark_active_model(run_id: str, topic_id: str, method: TrainingMethod) -> None:
    """Mark a training run as the active model, deactivating previous ones."""
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Deactivate previous active model for this topic+method
            cur.execute(
                """
                UPDATE "TrainingRun"
                SET "isActive" = false, "updatedAt" = %s
                WHERE "topicId" = %s AND method = %s AND "isActive" = true
                """,
                (now, topic_id, method.value),
            )
            # Activate the new one
            cur.execute(
                """
                UPDATE "TrainingRun"
                SET "isActive" = true, "updatedAt" = %s
                WHERE id = %s
                """,
                (now, run_id),
            )
            conn.commit()

    logger.info("Marked training run %s as active for topic %s", run_id, topic_id)


def get_training_run(run_id: str) -> TrainingRunResponse | None:
    """Fetch a single training run by ID."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM "TrainingRun" WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return _row_to_training_run_response(row)


def get_active_model(
    topic_id: str, method: TrainingMethod
) -> TrainingRunResponse | None:
    """Find the active model for a topic + method."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM "TrainingRun"
                WHERE "topicId" = %s AND method = %s AND "isActive" = true
                LIMIT 1
                """,
                (topic_id, method.value),
            )
            row = cur.fetchone()

    if not row:
        return None

    return _row_to_training_run_response(row)


def list_models(
    user_id: str | None = None, topic_id: str | None = None
) -> list[TrainingRunResponse]:
    """List completed training runs, optionally filtered by user and/or topic."""
    conditions: list[str] = ["status = %s"]
    params: list[Any] = [TrainingStatus.COMPLETED.value]

    if user_id:
        conditions.append('"userId" = %s')
        params.append(user_id)
    if topic_id:
        conditions.append('"topicId" = %s')
        params.append(topic_id)

    where = " AND ".join(conditions)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT * FROM "TrainingRun"
                WHERE {where}
                ORDER BY "createdAt" DESC
                """,
                params,
            )
            rows = cur.fetchall()

    return [_row_to_training_run_response(row) for row in rows]


def _row_to_training_run_response(row: dict[str, Any]) -> TrainingRunResponse:
    """Convert a DB row dict to a TrainingRunResponse."""
    config = row.get("config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = None

    metrics = row.get("metrics")
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except (json.JSONDecodeError, TypeError):
            metrics = None

    return TrainingRunResponse(
        id=row["id"],
        userId=row["userId"],
        topicId=row["topicId"],
        status=TrainingStatus(row["status"]),
        method=TrainingMethod(row["method"]),
        modelName=row["modelName"],
        version=row["version"],
        checkpointPath=row.get("checkpointPath"),
        baseModel=row["baseModel"],
        config=config,
        metrics=metrics,
        datasetSize=row.get("datasetSize"),
        error=row.get("error"),
        isActive=row.get("isActive", False),
        createdAt=row["createdAt"],
        updatedAt=row["updatedAt"],
        completedAt=row.get("completedAt"),
    )
