"""
Redis-backed event log for in-progress idea graph generations.

The orchestrator appends ordered events here while a LangGraph run is active so
SSE clients can replay missed updates and resume after transient disconnects.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import redis

from config import IDEA_GRAPH_STREAM_TTL_SECONDS
from models.schemas import (
    IdeaGraphGenerationMetadata,
    IdeaGraphGenerationStatus,
    IdeaGraphStreamEvent,
    IdeaGraphStreamEventType,
)
from utils.rate_limiter import _get_redis_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "idea_graph:generation"
_ACTIVE_PREFIX = "idea_graph:active"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdeaGraphEventStore:
    """Append-only event log plus generation metadata for idea graph runs."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    def _meta_key(self, generation_id: str) -> str:
        return f"{_KEY_PREFIX}:{generation_id}:meta"

    def _events_key(self, generation_id: str) -> str:
        return f"{_KEY_PREFIX}:{generation_id}:events"

    def _active_key(self, user_id: str, video_id: str) -> str:
        return f"{_ACTIVE_PREFIX}:{user_id}:{video_id}"

    def create_generation(
        self,
        *,
        generation_id: str,
        graph_id: str,
        user_id: str,
        video_id: str,
        started_at: datetime | None = None,
    ) -> IdeaGraphGenerationMetadata:
        timestamp = started_at or _utcnow()
        metadata = IdeaGraphGenerationMetadata(
            generation_id=generation_id,
            graph_id=graph_id,
            user_id=user_id,
            video_id=video_id,
            status=IdeaGraphGenerationStatus.GENERATING,
            started_at=timestamp,
            updated_at=timestamp,
        )
        meta_key = self._meta_key(generation_id)
        active_key = self._active_key(user_id, video_id)
        self._redis.hset(meta_key, mapping=self._serialize_metadata(metadata))
        self._redis.delete(self._events_key(generation_id))
        self._redis.set(active_key, generation_id)
        return metadata

    def get_generation(self, generation_id: str) -> IdeaGraphGenerationMetadata | None:
        raw = self._redis.hgetall(self._meta_key(generation_id))
        if not raw:
            return None
        return self._deserialize_metadata(raw)

    def get_active_generation(
        self,
        *,
        user_id: str,
        video_id: str,
    ) -> IdeaGraphGenerationMetadata | None:
        generation_id = self._decode(self._redis.get(self._active_key(user_id, video_id)))
        if not generation_id:
            return None
        metadata = self.get_generation(generation_id)
        if metadata is None:
            self._redis.delete(self._active_key(user_id, video_id))
            return None
        if metadata.status != IdeaGraphGenerationStatus.GENERATING:
            self._redis.delete(self._active_key(user_id, video_id))
            return None
        return metadata

    def set_run_metadata(
        self,
        generation_id: str,
        *,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> IdeaGraphGenerationMetadata:
        metadata = self._require_generation(generation_id)
        updated = metadata.model_copy(
            update={
                "thread_id": thread_id or metadata.thread_id,
                "run_id": run_id or metadata.run_id,
                "updated_at": _utcnow(),
            }
        )
        self._redis.hset(self._meta_key(generation_id), mapping=self._serialize_metadata(updated))
        return updated

    def append_event(
        self,
        generation_id: str,
        *,
        event_type: IdeaGraphStreamEventType,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> IdeaGraphStreamEvent:
        metadata = self._require_generation(generation_id)
        event_timestamp = timestamp or _utcnow()
        with self._redis.pipeline() as pipe:
            pipe.hincrby(self._meta_key(generation_id), "last_event_id", 1)
            [event_id] = pipe.execute()

        event = IdeaGraphStreamEvent(
            generation_id=generation_id,
            event_id=int(event_id),
            user_id=metadata.user_id,
            video_id=metadata.video_id,
            timestamp=event_timestamp,
            type=event_type,
            payload=payload or {},
        )

        with self._redis.pipeline() as pipe:
            pipe.rpush(self._events_key(generation_id), event.model_dump_json())
            pipe.hset(
                self._meta_key(generation_id),
                mapping={
                    "updated_at": event_timestamp.isoformat(),
                    "status": metadata.status.value,
                },
            )
            pipe.execute()

        return event

    def list_events_after(
        self,
        generation_id: str,
        *,
        after_event_id: int = 0,
    ) -> list[IdeaGraphStreamEvent]:
        start_index = max(after_event_id, 0)
        raw_items = self._redis.lrange(self._events_key(generation_id), start_index, -1)
        events: list[IdeaGraphStreamEvent] = []
        for raw_item in raw_items:
            try:
                data = json.loads(self._decode(raw_item))
            except json.JSONDecodeError:
                logger.exception("Failed to decode idea graph stream event for %s", generation_id)
                continue
            events.append(IdeaGraphStreamEvent.model_validate(data))
        return events

    def mark_completed(
        self,
        generation_id: str,
        *,
        payload: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> IdeaGraphStreamEvent:
        event = self.append_event(
            generation_id,
            event_type="completed",
            payload=payload,
            timestamp=completed_at,
        )
        self._mark_terminal(
            generation_id,
            status=IdeaGraphGenerationStatus.COMPLETED,
            completed_at=event.timestamp,
            error=None,
        )
        return event

    def mark_failed(
        self,
        generation_id: str,
        *,
        error: str,
        payload: dict[str, Any] | None = None,
        failed_at: datetime | None = None,
    ) -> IdeaGraphStreamEvent:
        payload = {"error": error, **(payload or {})}
        event = self.append_event(
            generation_id,
            event_type="failed",
            payload=payload,
            timestamp=failed_at,
        )
        self._mark_terminal(
            generation_id,
            status=IdeaGraphGenerationStatus.FAILED,
            completed_at=event.timestamp,
            error=error,
        )
        return event

    def _mark_terminal(
        self,
        generation_id: str,
        *,
        status: IdeaGraphGenerationStatus,
        completed_at: datetime,
        error: str | None,
    ) -> IdeaGraphGenerationMetadata:
        metadata = self._require_generation(generation_id)
        updated = metadata.model_copy(
            update={
                "status": status,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "error": error,
            }
        )
        meta_key = self._meta_key(generation_id)
        events_key = self._events_key(generation_id)
        active_key = self._active_key(updated.user_id, updated.video_id)
        with self._redis.pipeline() as pipe:
            pipe.hset(meta_key, mapping=self._serialize_metadata(updated))
            pipe.delete(active_key)
            pipe.expire(meta_key, IDEA_GRAPH_STREAM_TTL_SECONDS)
            pipe.expire(events_key, IDEA_GRAPH_STREAM_TTL_SECONDS)
            pipe.execute()
        return updated

    def _require_generation(self, generation_id: str) -> IdeaGraphGenerationMetadata:
        metadata = self.get_generation(generation_id)
        if metadata is None:
            raise KeyError(f"Unknown idea graph generation id: {generation_id}")
        return metadata

    def _serialize_metadata(self, metadata: IdeaGraphGenerationMetadata) -> dict[str, str]:
        payload = metadata.model_dump(mode="json")
        payload["status"] = metadata.status.value
        return {key: json.dumps(value) if isinstance(value, bool) else str(value) for key, value in payload.items()}

    def _deserialize_metadata(self, raw: dict[Any, Any]) -> IdeaGraphGenerationMetadata:
        decoded = {self._decode(key): self._decode(value) for key, value in raw.items()}
        return IdeaGraphGenerationMetadata(
            generation_id=decoded["generation_id"],
            graph_id=decoded["graph_id"],
            user_id=decoded["user_id"],
            video_id=decoded["video_id"],
            status=IdeaGraphGenerationStatus(decoded["status"]),
            started_at=datetime.fromisoformat(decoded["started_at"]),
            updated_at=datetime.fromisoformat(decoded["updated_at"]),
            completed_at=(
                datetime.fromisoformat(decoded["completed_at"])
                if decoded.get("completed_at") and decoded["completed_at"] != "None"
                else None
            ),
            error=None if decoded.get("error") in (None, "None", "") else decoded["error"],
            last_event_id=int(decoded.get("last_event_id", "0")),
            thread_id=None if decoded.get("thread_id") in (None, "None", "") else decoded["thread_id"],
            run_id=None if decoded.get("run_id") in (None, "None", "") else decoded["run_id"],
        )

    def _decode(self, value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

@lru_cache(maxsize=1)
def get_idea_graph_event_store() -> IdeaGraphEventStore:
    return IdeaGraphEventStore(_get_redis_client())
