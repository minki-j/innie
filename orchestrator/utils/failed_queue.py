"""
Redis-backed dead-letter queue for failed Prefect tasks/flows.

When a Prefect task or flow exhausts all retries, an ``on_failure`` hook
pushes the job payload here so it can be inspected and re-processed later.

Each logical job type gets its own Redis list key:
    ``failed_jobs:{queue_name}``

Usage (in an on_failure hook)::

    from utils.failed_queue import get_failed_queue

    def _on_failure(task, task_run, state):
        get_failed_queue("process_video_for_funnel").push({
            "video_id": task_run.parameters["video_id"],
            "funnel_id": task_run.parameters["funnel_id"],
            "error": str(state.result(raise_on_failure=False)),
            "failed_at": datetime.utcnow().isoformat(),
        })

Draining::

    jobs = get_failed_queue("process_video_for_funnel").pop_all()
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import redis

from utils.rate_limiter import _get_redis_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "failed_jobs"


class FailedJobQueue:
    """
    FIFO dead-letter queue for one job type, backed by a Redis list.

    Items are pushed to the tail (RPUSH) and popped from the head (LPOP)
    so the queue preserves insertion order.
    """

    def __init__(self, redis_client: redis.Redis, queue_name: str) -> None:
        self._redis = redis_client
        self._queue_name = queue_name
        self._key = f"{_KEY_PREFIX}:{queue_name}"

    def push(self, payload: dict[str, Any]) -> None:
        """Append a failed job payload to the queue."""
        self._redis.rpush(self._key, json.dumps(payload))
        logger.warning(
            "Dead-letter queue '%s': pushed failed job (%s)",
            self._queue_name,
            {k: v for k, v in payload.items() if k != "error"},
        )

    def pop_all(self) -> list[dict[str, Any]]:
        """
        Atomically drain the entire queue and return all payloads.

        Uses a pipeline + LRANGE/DELETE to avoid partial reads under concurrency.
        """
        with self._redis.pipeline() as pipe:
            pipe.lrange(self._key, 0, -1)
            pipe.delete(self._key)
            raw_items, _ = pipe.execute()

        jobs = []
        for raw in raw_items:
            try:
                jobs.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.error(
                    "Dead-letter queue '%s': failed to decode payload: %r",
                    self._queue_name,
                    raw,
                )
        return jobs

    def peek(self, count: int = 10) -> list[dict[str, Any]]:
        """Return up to ``count`` items without removing them."""
        raw_items = self._redis.lrange(self._key, 0, count - 1)
        jobs = []
        for raw in raw_items:
            try:
                jobs.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return jobs

    def length(self) -> int:
        """Return the number of items currently in the queue."""
        return self._redis.llen(self._key)


# ── Per-queue singletons ──────────────────────────────────────

_QUEUES: dict[str, FailedJobQueue] = {}


def get_failed_queue(queue_name: str) -> FailedJobQueue:
    """Return (and cache) the ``FailedJobQueue`` for the given name."""
    if queue_name not in _QUEUES:
        _QUEUES[queue_name] = FailedJobQueue(_get_redis_client(), queue_name)
    return _QUEUES[queue_name]
