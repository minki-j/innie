from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from flows.idea_graph import generate_idea_graph_for_video


class _FakeThreadsClient:
    def __init__(self) -> None:
        self.get_state_call_count = 0
        self.get_call_count = 0

    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get(self, thread_id: str) -> dict[str, str]:
        self.get_call_count += 1
        return {"thread_id": thread_id, "status": "busy"}

    def get_state(self, thread_id: str) -> dict:
        self.get_state_call_count += 1
        return {
            "values": {
                "result_graph": {
                    "nodes": [
                        {
                            "id": "node_a",
                            "type": "CLAIM",
                            "title": "Main claim",
                            "content": None,
                            "x": 0,
                            "y": 0,
                            "collapsed": False,
                            "transcript_sources": [],
                        }
                    ],
                    "edges": [],
                }
            }
        }


class _FakeRunsClient:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        on_run_created = kwargs.get("on_run_created")
        if on_run_created:
            on_run_created({"run_id": "run_123"})
        yield {"type": "metadata", "ns": [], "data": {"run_id": "run_123"}}
        yield {
            "type": "custom",
            "ns": [],
            "data": {
                "event_type": "node_added",
                "payload": {
                    "node": {
                        "id": "node_a",
                        "type": "CLAIM",
                        "title": "Main claim",
                        "content": None,
                        "x": 0,
                        "y": 0,
                        "collapsed": False,
                        "transcriptSources": [],
                    }
                },
            },
        }
        yield {
            "type": "custom",
            "ns": [],
            "data": {
                "event_type": "task_completed",
                "payload": {
                    "result_graph": {
                        "nodes": [
                            {
                                "id": "node_a",
                                "type": "CLAIM",
                                "title": "Main claim",
                                "content": None,
                                "x": 0,
                                "y": 0,
                                "collapsed": False,
                                "transcriptSources": [],
                            }
                        ],
                        "edges": [],
                    }
                },
            },
        }


class _FakeLangGraphClient:
    def __init__(self) -> None:
        self.threads = _FakeThreadsClient()
        self.runs = _FakeRunsClient()


class _BlockingRunsStream:
    def __init__(self) -> None:
        self._yielded_metadata = False
        self.release = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        if not self._yielded_metadata:
            self._yielded_metadata = True
            return {"type": "metadata", "ns": [], "data": {"run_id": "run_123"}}
        self.release.wait(timeout=1)
        raise StopIteration


class _BlockingThreadsClient:
    def __init__(self, stream: _BlockingRunsStream) -> None:
        self._stream = stream
        self.get_state_call_count = 0
        self.get_call_count = 0

    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get(self, thread_id: str) -> dict[str, str]:
        self.get_call_count += 1
        self._stream.release.set()
        return {"thread_id": thread_id, "status": "idle"}

    def get_state(self, thread_id: str) -> dict:
        self.get_state_call_count += 1
        self._stream.release.set()
        return {
            "values": {
                "result_graph": {
                    "nodes": [],
                    "edges": [],
                }
            }
        }


class _BlockingRunsClient:
    def __init__(self, stream: _BlockingRunsStream) -> None:
        self._stream = stream

    def stream(self, **kwargs):
        on_run_created = kwargs.get("on_run_created")
        if on_run_created:
            on_run_created({"run_id": "run_123"})
        return self._stream


class _BlockingLangGraphClient:
    def __init__(self) -> None:
        self.stream = _BlockingRunsStream()
        self.threads = _BlockingThreadsClient(self.stream)
        self.runs = _BlockingRunsClient(self.stream)


class _InterruptedThreadsClient:
    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get(self, thread_id: str) -> dict[str, str]:
        return {"thread_id": thread_id, "status": "interrupted"}

    def get_state(self, thread_id: str) -> dict:
        return {"values": {"result_graph": None}}


class _InterruptedRunsClient:
    def stream(self, **kwargs):
        on_run_created = kwargs.get("on_run_created")
        if on_run_created:
            on_run_created({"run_id": "run_123"})
        yield {"type": "metadata", "ns": [], "data": {"run_id": "run_123"}}


class _InterruptedLangGraphClient:
    def __init__(self) -> None:
        self.threads = _InterruptedThreadsClient()
        self.runs = _InterruptedRunsClient()


class _TaskErrorThreadsClient:
    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}


class _TaskErrorRunsClient:
    def stream(self, **kwargs):
        on_run_created = kwargs.get("on_run_created")
        if on_run_created:
            on_run_created({"run_id": "run_123"})
        yield {"type": "metadata", "ns": [], "data": {"run_id": "run_123"}}
        yield {
            "type": "tasks",
            "ns": [],
            "data": {
                "status": "error",
                "message": "task stream exploded",
            },
        }


class _TaskErrorLangGraphClient:
    def __init__(self) -> None:
        self.threads = _TaskErrorThreadsClient()
        self.runs = _TaskErrorRunsClient()


class _UnavailableStatusThreadsClient:
    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get(self, thread_id: str) -> dict[str, str]:
        return {"thread_id": thread_id, "status": "busy"}

    def get_state(self, thread_id: str) -> dict:
        raise RuntimeError("status check unavailable")


class _UnavailableStatusRunsClient:
    def stream(self, **kwargs):
        on_run_created = kwargs.get("on_run_created")
        if on_run_created:
            on_run_created({"run_id": "run_123"})
        yield {"type": "metadata", "ns": [], "data": {"run_id": "run_123"}}


class _UnavailableStatusLangGraphClient:
    def __init__(self) -> None:
        self.threads = _UnavailableStatusThreadsClient()
        self.runs = _UnavailableStatusRunsClient()


class IdeaGraphFlowTests(unittest.TestCase):
    @patch("flows.idea_graph.STREAM_INACTIVITY_TIMEOUT_SECONDS", 0.01)
    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.replace_idea_graph")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_streamed_generation_buffers_events_and_persists_once(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        replace_idea_graph: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([{"text": "hello", "start_sec": 0, "end_sec": 1}], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        fake_client = _FakeLangGraphClient()
        get_sync_client.return_value = fake_client
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        result = generate_idea_graph_for_video(
            generation_id="gen_123",
            graph_id="graph_123",
            user_id="user_123",
            video_id="video_123",
        )

        self.assertEqual(result["generation_id"], "gen_123")
        replace_idea_graph.assert_called_once_with(
            graph_id="graph_123",
            snapshot=unittest.mock.ANY,
        )
        event_store.set_run_metadata.assert_any_call("gen_123", thread_id="thread_123")
        event_store.set_run_metadata.assert_any_call("gen_123", run_id="run_123")
        event_store.append_event.assert_any_call(
            "gen_123",
            event_type="generation_started",
            payload={
                "video_title": "Main title",
            },
        )
        event_store.append_event.assert_any_call(
            "gen_123",
            event_type="node_added",
            payload={
                "node": {
                    "id": "node_a",
                    "type": "CLAIM",
                    "title": "Main claim",
                    "content": None,
                    "x": 0,
                    "y": 0,
                    "collapsed": False,
                    "transcriptSources": [],
                }
            },
        )
        event_store.mark_completed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)
        set_idea_graph_generation_status.assert_any_call(
            graph_id="graph_123",
            status=unittest.mock.ANY,
            error=None,
        )
        self.assertIsNotNone(fake_client.runs.last_kwargs)
        self.assertEqual(
            fake_client.runs.last_kwargs["input"]["current_graph"],
            {"nodes": [], "edges": []},
        )
        self.assertEqual(
            fake_client.runs.last_kwargs["stream_mode"],
            ["custom", "tasks"],
        )
        self.assertEqual(fake_client.threads.get_state_call_count, 0)
        self.assertEqual(fake_client.threads.get_call_count, 0)

    @patch("flows.idea_graph.STREAM_INACTIVITY_TIMEOUT_SECONDS", 0.01)
    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.replace_idea_graph")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_generation_succeeds_when_result_arrives_while_stream_thread_is_active(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        replace_idea_graph: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([{"text": "hello", "start_sec": 0, "end_sec": 1}], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _BlockingLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        result = generate_idea_graph_for_video(
            generation_id="gen_123",
            graph_id="graph_123",
            user_id="user_123",
            video_id="video_123",
        )

        self.assertEqual(result["status"], "completed")
        replace_idea_graph.assert_called_once_with(
            graph_id="graph_123",
            snapshot=unittest.mock.ANY,
        )
        self.assertEqual(
            get_sync_client.return_value.threads.get_state_call_count,
            1,
        )
        self.assertEqual(
            get_sync_client.return_value.threads.get_call_count,
            1,
        )
        event_store.mark_completed.assert_called_once()
        event_store.mark_failed.assert_not_called()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)

    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_failed_generation_marks_terminal_failure(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.side_effect = RuntimeError("langgraph unavailable")
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        with self.assertRaises(RuntimeError):
            generate_idea_graph_for_video(
                generation_id="gen_123",
                graph_id="graph_123",
                user_id="user_123",
                video_id="video_123",
            )

        event_store.mark_failed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)
        set_idea_graph_generation_status.assert_any_call(
            graph_id="graph_123",
            status=unittest.mock.ANY,
            error="langgraph unavailable",
        )

    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_task_error_fails_generation_immediately(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _TaskErrorLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        with self.assertRaisesRegex(RuntimeError, "LangGraph task failed: task stream exploded"):
            generate_idea_graph_for_video(
                generation_id="gen_123",
                graph_id="graph_123",
                user_id="user_123",
                video_id="video_123",
            )

        event_store.mark_failed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)

    @patch("flows.idea_graph.STREAM_INACTIVITY_TIMEOUT_SECONDS", 0.01)
    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_status_check_failure_marks_terminal_failure(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _UnavailableStatusLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        with self.assertRaisesRegex(
            RuntimeError,
            "LangGraph server became unreachable while checking thread thread_123",
        ):
            generate_idea_graph_for_video(
                generation_id="gen_123",
                graph_id="graph_123",
                user_id="user_123",
                video_id="video_123",
            )

        event_store.mark_failed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)

    @patch("flows.idea_graph.STREAM_INACTIVITY_TIMEOUT_SECONDS", 0.01)
    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_interrupted_thread_fails_before_timeout(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_rate_limiter: MagicMock,
        get_sync_client: MagicMock,
        set_idea_graph_generation_status: MagicMock,
        get_idea_graph_event_store: MagicMock,
    ) -> None:
        get_video_for_idea_graph.return_value = {
            "id": "video_123",
            "title": "Main title",
            "transcript": "hello world",
        }
        fetch_transcript_segments.return_value = ([], "ok")
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _InterruptedLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        with self.assertRaisesRegex(
            RuntimeError,
            "LangGraph thread thread_123 was interrupted before producing result_graph",
        ):
            generate_idea_graph_for_video(
                generation_id="gen_123",
                graph_id="graph_123",
                user_id="user_123",
                video_id="video_123",
            )

        event_store.mark_failed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)


if __name__ == "__main__":
    unittest.main()
