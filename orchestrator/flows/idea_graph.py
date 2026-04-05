from __future__ import annotations

import logging
import threading
import time
from typing import Any

from langgraph_sdk import get_sync_client

from config import LANGGRAPH_API_KEY, LANGGRAPH_API_URL
from models.schemas import (
    IdeaGraphAgentCustomEvent,
    IdeaGraphGenerationInput,
    IdeaGraphGenerationStatus,
    IdeaGraphSnapshot,
)
from tasks.db import (
    get_video_for_idea_graph,
    replace_idea_graph,
    set_idea_graph_generation_status,
)
from tasks.youtube import fetch_transcript_segments
from utils.idea_graph_events import get_idea_graph_event_store
from utils.rate_limiter import get_rate_limiter

from prefect_github.repository import GitHubRepository

github_repository_block = GitHubRepository.load("innie-github-repo-read-access")

logger = logging.getLogger(__name__)

STREAM_INACTIVITY_TIMEOUT_SECONDS = 15.0
GENERATION_TIMEOUT_SECONDS = 600.0
WAIT_LOG_INTERVAL_SECONDS = 10.0


class IdeaGraphGenerationFailure(RuntimeError):
    """Expected terminal generation failure that should not dump duplicate traces."""


def _print_generation_log(generation_id: str, message: str) -> None:
    print(f"[idea_graph:{generation_id}] {message}", flush=True)


def _get_mapping_or_attr(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _normalize_status(status: Any) -> str | None:
    if status is None:
        return None
    status_value = getattr(status, "value", status)
    if status_value is None:
        return None
    return str(status_value).strip().lower()


def _get_result_graph(state: Any) -> Any:
    values = _get_mapping_or_attr(state, "values")
    if isinstance(values, dict):
        return values.get("result_graph")
    return _get_mapping_or_attr(values, "result_graph")


def _extract_task_error_message(task_data: Any) -> str | None:
    if task_data is None:
        return None
    if isinstance(task_data, str):
        task_data = task_data.strip()
        return task_data or None
    if isinstance(task_data, BaseException):
        return str(task_data)
    if isinstance(task_data, list | tuple):
        for item in task_data:
            error_message = _extract_task_error_message(item)
            if error_message:
                return error_message
        return None
    if not isinstance(task_data, dict):
        return None

    for key in ("error", "errors", "exception"):
        error_message = _extract_task_error_message(task_data.get(key))
        if error_message:
            return error_message

    status = _normalize_status(task_data.get("status"))
    if status in {"error", "failed", "interrupted"}:
        for key in ("message", "reason", "name"):
            error_message = _extract_task_error_message(task_data.get(key))
            if error_message:
                return error_message
        return f"task status={status}"

    for key in ("task", "tasks", "data", "payload", "result"):
        error_message = _extract_task_error_message(task_data.get(key))
        if error_message:
            return error_message

    return None


def _get_langgraph_thread_snapshot(
    client: Any,
    *,
    thread_id: str,
) -> tuple[Any, str | None]:
    try:
        state = client.threads.get_state(thread_id=thread_id)
        thread_status = _normalize_status(
            _get_mapping_or_attr(
                client.threads.get(thread_id=thread_id),
                "status",
            )
        )
        return state, thread_status
    except Exception as exc:
        raise IdeaGraphGenerationFailure(
            f"LangGraph server became unreachable while checking thread {thread_id}"
        ) from exc


def generate_idea_graph_for_video(
    generation_id: str,
    graph_id: str,
    user_id: str,
    video_id: str,
) -> dict[str, Any]:
    """
    Generate an idea graph for a specific user/video pair via LangGraph.

    The LangGraph agent reads transcript chunks and returns a full replacement
    graph snapshot for a newly created graph version.
    """
    event_store = get_idea_graph_event_store()
    _print_generation_log(
        generation_id,
        f"starting generation for user={user_id} video={video_id}",
    )
    set_idea_graph_generation_status(
        graph_id=graph_id,
        status=IdeaGraphGenerationStatus.GENERATING,
        error=None,
    )

    try:
        video = get_video_for_idea_graph(video_id)
        if not video:
            raise ValueError(f"Video not found: {video_id}")
        if not video["transcript"]:
            raise ValueError(f"Video {video_id} does not have a transcript")

        transcript_segments, segment_status = fetch_transcript_segments(video_id)
        _print_generation_log(
            generation_id,
            "transcript segments "
            f"{'loaded' if transcript_segments else 'missing'} ({segment_status})",
        )
        logger.info(
            "Idea graph transcript segments for %s: %s (%s)",
            video_id,
            "loaded" if transcript_segments else "missing",
            segment_status,
        )

        _print_generation_log(
            generation_id,
            "starting generation from an empty graph seed",
        )
        event_store.append_event(
            generation_id,
            event_type="generation_started",
            payload={
                "video_title": video["title"],
            },
        )
        graph_input = IdeaGraphGenerationInput(
            user_id=user_id,
            video_id=video_id,
            video_title=video["title"],
            transcript=video["transcript"],
            transcript_segments=transcript_segments or [],
            current_graph=IdeaGraphSnapshot(),
        )

        logger.info(
            "Calling build_idea_graph LangGraph agent for user=%s video=%s (url=%s)",
            user_id,
            video_id,
            LANGGRAPH_API_URL,
        )
        _print_generation_log(
            generation_id, f"waiting for langgraph rate limiter at {LANGGRAPH_API_URL}"
        )

        get_rate_limiter("langgraph").acquire()
        _print_generation_log(
            generation_id, "rate limiter acquired; creating langgraph client and thread"
        )

        client = get_sync_client(
            url=LANGGRAPH_API_URL,
            api_key=LANGGRAPH_API_KEY or None,
        )
        thread = client.threads.create()
        event_store.set_run_metadata(generation_id, thread_id=thread["thread_id"])
        _print_generation_log(
            generation_id,
            f"created langgraph thread {thread['thread_id']}",
        )

        def _on_run_created(metadata: dict[str, Any]) -> None:
            run_id = metadata.get("run_id")
            if run_id:
                event_store.set_run_metadata(generation_id, run_id=run_id)
                _print_generation_log(generation_id, f"langgraph run created: {run_id}")

        stream_iterator = client.runs.stream(
            thread_id=thread["thread_id"],
            assistant_id="build_idea_graph",
            input=graph_input.model_dump(mode="json"),
            stream_mode=["custom", "tasks"],
            stream_resumable=True,
            on_disconnect="continue",
            version="v2",
            on_run_created=_on_run_created,
        )
        stream_error: list[Exception] = []
        # The stream thread updates heartbeat/error state and wakes the main
        # loop so we only fall back to status checks after real inactivity.
        stream_condition = threading.Condition()
        stream_state = {
            "closed": False,
            "last_activity_at": time.monotonic(),
            "result_graph": None,
            "task_completed": False,
        }
        stop_stream = threading.Event()
        stream_thread: threading.Thread | None = None

        def _notify_stream_state(
            *,
            mark_activity: bool = False,
            closed: bool = False,
            task_completed: bool = False,
            result_graph: Any | None = None,
            error: Exception | None = None,
        ) -> None:
            # Keep shared stream state and notifications under one lock so the
            # waiting loop sees a consistent heartbeat/error snapshot.
            with stream_condition:
                if mark_activity:
                    stream_state["last_activity_at"] = time.monotonic()
                if closed:
                    stream_state["closed"] = True
                if task_completed:
                    stream_state["task_completed"] = True
                if result_graph is not None:
                    stream_state["result_graph"] = result_graph
                if error is not None and not stop_stream.is_set():
                    stream_error.append(error)
                stream_condition.notify_all()

        def _consume_stream() -> None:
            try:
                for part in stream_iterator:
                    if stop_stream.is_set():
                        break
                    _notify_stream_state(mark_activity=True)
                    part_type = part.get("type")
                    if part_type == "metadata":
                        run_id = part.get("data", {}).get("run_id")
                        if run_id:
                            event_store.set_run_metadata(generation_id, run_id=run_id)
                            _print_generation_log(
                                generation_id, f"received metadata for run {run_id}"
                            )
                        continue
                    if part_type != "custom":
                        if part_type == "tasks":
                            task_error = _extract_task_error_message(part.get("data"))
                            if task_error:
                                raise IdeaGraphGenerationFailure(
                                    f"LangGraph task failed: {task_error}"
                                )
                        continue

                    custom_event = IdeaGraphAgentCustomEvent.model_validate(
                        part.get("data") or {}
                    )
                    _print_generation_log(
                        generation_id,
                        f"received custom event: {custom_event.event_type}",
                    )
                    if custom_event.event_type == "task_completed":
                        _notify_stream_state(
                            task_completed=True,
                            result_graph=custom_event.payload.get("result_graph"),
                        )
                        continue
                    event_store.append_event(
                        generation_id,
                        event_type=custom_event.event_type,
                        payload=custom_event.payload,
                    )
            except Exception as exc:  # pragma: no cover - exercised in integration
                _notify_stream_state(error=exc, closed=True)
            else:
                _notify_stream_state(closed=True)

        try:
            stream_thread = threading.Thread(
                target=_consume_stream,
                name=f"idea-graph-stream-{generation_id}",
                daemon=True,
            )
            stream_thread.start()
            _print_generation_log(
                generation_id,
                "stream consumer started; waiting for result_graph via stream activity",
            )

            result_graph = None
            deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
            last_status_check_at = 0.0
            next_wait_log_at = time.monotonic()
            while True:
                now = time.monotonic()
                if now >= deadline:
                    break

                with stream_condition:
                    pending_error = stream_error[0] if stream_error else None
                    last_activity_at = float(stream_state["last_activity_at"])
                    streamed_result_graph = stream_state["result_graph"]
                    task_completed = bool(stream_state["task_completed"])
                    if task_completed and streamed_result_graph is None:
                        stream_state["task_completed"] = False

                if pending_error:
                    raise pending_error
                if streamed_result_graph is not None:
                    result_graph = streamed_result_graph
                    _print_generation_log(
                        generation_id,
                        "result_graph received from task_completed stream event",
                    )
                    break

                if now >= next_wait_log_at:
                    next_wait_log_at = now + WAIT_LOG_INTERVAL_SECONDS

                if task_completed:
                    _print_generation_log(
                        generation_id,
                        "task_completed signal received without inline result_graph; checking langgraph thread state immediately",
                    )
                    state, thread_status = _get_langgraph_thread_snapshot(
                        client,
                        thread_id=thread["thread_id"],
                    )
                    result_graph = _get_result_graph(state)
                    if result_graph:
                        _print_generation_log(
                            generation_id,
                            "result_graph detected immediately after task_completed signal",
                        )
                        break

                    last_status_check_at = time.monotonic()
                    if thread_status == "interrupted":
                        raise IdeaGraphGenerationFailure(
                            f"LangGraph thread {thread['thread_id']} was interrupted before producing result_graph"
                        )
                    if thread_status == "idle":
                        raise IdeaGraphGenerationFailure(
                            f"LangGraph thread {thread['thread_id']} became idle without result_graph"
                        )

                next_status_check_at = (
                    max(last_activity_at, last_status_check_at)
                    + STREAM_INACTIVITY_TIMEOUT_SECONDS
                )
                if now >= next_status_check_at:
                    _print_generation_log(
                        generation_id,
                        "stream quiet for "
                        f"{STREAM_INACTIVITY_TIMEOUT_SECONDS:g}s; "
                        "checking langgraph thread state",
                    )
                    state, thread_status = _get_langgraph_thread_snapshot(
                        client,
                        thread_id=thread["thread_id"],
                    )
                    result_graph = _get_result_graph(state)
                    if result_graph:
                        _print_generation_log(
                            generation_id, "result_graph detected from langgraph state"
                        )
                        break

                    last_status_check_at = time.monotonic()
                    if thread_status == "interrupted":
                        raise IdeaGraphGenerationFailure(
                            f"LangGraph thread {thread['thread_id']} was interrupted before producing result_graph"
                        )
                    if thread_status == "idle":
                        try:
                            final_state = client.threads.get_state(
                                thread_id=thread["thread_id"]
                            )
                        except Exception as exc:
                            raise IdeaGraphGenerationFailure(
                                "LangGraph server became unreachable while reading "
                                f"final state for thread {thread['thread_id']}"
                            ) from exc
                        result_graph = _get_result_graph(final_state)
                        if result_graph:
                            _print_generation_log(
                                generation_id,
                                "result_graph detected from idle thread state",
                            )
                            break
                        raise IdeaGraphGenerationFailure(
                            f"LangGraph thread {thread['thread_id']} became idle without result_graph"
                        )
                    continue

                # Sleep until a stream update/error arrives or until it's time
                # to log / do the inactivity-based fallback status check.
                wait_until = min(deadline, next_wait_log_at, next_status_check_at)
                wait_timeout = max(0.0, wait_until - time.monotonic())
                with stream_condition:
                    if stream_error:
                        continue
                    stream_condition.wait(timeout=wait_timeout)
        finally:
            stop_stream.set()
            if stream_thread is not None:
                stream_thread.join(timeout=2)
                if stream_thread.is_alive():
                    _print_generation_log(
                        generation_id,
                        "stream consumer still draining after join timeout",
                    )
                    logger.warning(
                        "Idea graph stream thread still draining after completion for generation=%s",
                        generation_id,
                    )

        if not result_graph:
            raise TimeoutError(
                "LangGraph run did not produce result_graph before timeout"
            )

        snapshot = IdeaGraphSnapshot.model_validate(result_graph)
        replace_idea_graph(graph_id=graph_id, snapshot=snapshot)
        _print_generation_log(
            generation_id,
            f"persisted snapshot with {len(snapshot.nodes)} nodes and {len(snapshot.edges)} edges",
        )
        set_idea_graph_generation_status(
            graph_id=graph_id,
            status=IdeaGraphGenerationStatus.COMPLETED,
            error=None,
        )
        event_store.mark_completed(
            generation_id,
            payload={
                "node_count": len(snapshot.nodes),
                "edge_count": len(snapshot.edges),
            },
        )
        _print_generation_log(generation_id, "generation completed successfully")

        return {
            "generation_id": generation_id,
            "status": "completed",
            "user_id": user_id,
            "video_id": video_id,
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
        }
    except Exception as exc:
        _print_generation_log(generation_id, f"generation failed: {exc}")
        if isinstance(exc, IdeaGraphGenerationFailure):
            logger.warning(
                "Idea graph generation failed for user=%s video=%s: %s",
                user_id,
                video_id,
                exc,
            )
        else:
            logger.exception(
                "Failed to generate idea graph for user=%s video=%s",
                user_id,
                video_id,
            )
        set_idea_graph_generation_status(
            graph_id=graph_id,
            status=IdeaGraphGenerationStatus.FAILED,
            error=str(exc),
        )
        event_store.mark_failed(generation_id, error=str(exc))
        raise
