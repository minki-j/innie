from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from flows.idea_graph import generate_idea_graph_for_video
from models.schemas import IdeaGraphSnapshot


class _FakeThreadsClient:
    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get_state(self, thread_id: str) -> dict:
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
    def stream(self, **kwargs):
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

    def create(self) -> dict[str, str]:
        return {"thread_id": "thread_123"}

    def get_state(self, thread_id: str) -> dict:
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


class IdeaGraphFlowTests(unittest.TestCase):
    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.replace_idea_graph")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.get_idea_graph_snapshot")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_streamed_generation_buffers_events_and_persists_once(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_idea_graph_snapshot: MagicMock,
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
        get_idea_graph_snapshot.return_value = IdeaGraphSnapshot()
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _FakeLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        result = generate_idea_graph_for_video(
            generation_id="gen_123",
            user_id="user_123",
            video_id="video_123",
            replace_existing=True,
        )

        self.assertEqual(result["generation_id"], "gen_123")
        replace_idea_graph.assert_called_once()
        event_store.set_run_metadata.assert_any_call("gen_123", thread_id="thread_123")
        event_store.set_run_metadata.assert_any_call("gen_123", run_id="run_123")
        event_store.append_event.assert_any_call(
            "gen_123",
            event_type="generation_started",
            payload={
                "replace_existing": True,
                "video_title": "Main title",
                "initial_graph": {"nodes": [], "edges": []},
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

    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.replace_idea_graph")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.get_idea_graph_snapshot")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_generation_succeeds_when_result_arrives_while_stream_thread_is_active(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_idea_graph_snapshot: MagicMock,
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
        get_idea_graph_snapshot.return_value = IdeaGraphSnapshot()
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.return_value = _BlockingLangGraphClient()
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        result = generate_idea_graph_for_video(
            generation_id="gen_123",
            user_id="user_123",
            video_id="video_123",
            replace_existing=True,
        )

        self.assertEqual(result["status"], "completed")
        replace_idea_graph.assert_called_once()
        event_store.mark_completed.assert_called_once()
        event_store.mark_failed.assert_not_called()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)

    @patch("flows.idea_graph.get_idea_graph_event_store")
    @patch("flows.idea_graph.set_idea_graph_generation_status")
    @patch("flows.idea_graph.get_sync_client")
    @patch("flows.idea_graph.get_rate_limiter")
    @patch("flows.idea_graph.get_idea_graph_snapshot")
    @patch("flows.idea_graph.fetch_transcript_segments")
    @patch("flows.idea_graph.get_video_for_idea_graph")
    def test_failed_generation_marks_terminal_failure(
        self,
        get_video_for_idea_graph: MagicMock,
        fetch_transcript_segments: MagicMock,
        get_idea_graph_snapshot: MagicMock,
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
        get_idea_graph_snapshot.return_value = IdeaGraphSnapshot()
        get_rate_limiter.return_value.acquire.return_value = None
        get_sync_client.side_effect = RuntimeError("langgraph unavailable")
        event_store = MagicMock()
        get_idea_graph_event_store.return_value = event_store

        with self.assertRaises(RuntimeError):
            generate_idea_graph_for_video(
                generation_id="gen_123",
                user_id="user_123",
                video_id="video_123",
                replace_existing=True,
            )

        event_store.mark_failed.assert_called_once()
        self.assertEqual(set_idea_graph_generation_status.call_count, 2)


if __name__ == "__main__":
    unittest.main()
