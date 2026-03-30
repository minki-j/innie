from __future__ import annotations

import unittest

import fakeredis

from models.schemas import IdeaGraphGenerationStatus
from utils.idea_graph_events import IdeaGraphEventStore


class IdeaGraphEventStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.redis = fakeredis.FakeRedis(decode_responses=False)
        self.store = IdeaGraphEventStore(self.redis)
        self.metadata = self.store.create_generation(
            generation_id="gen_123",
            graph_id="graph_123",
            user_id="user_123",
            video_id="video_123",
        )

    def test_append_and_replay_events_in_order(self) -> None:
        first = self.store.append_event(
            "gen_123",
            event_type="generation_started",
            payload={},
        )
        second = self.store.append_event(
            "gen_123",
            event_type="node_added",
            payload={"node": {"id": "node_a", "type": "CLAIM", "title": "A", "content": None, "x": 0, "y": 0, "collapsed": False, "transcriptSources": []}},
        )

        replayed = self.store.list_events_after("gen_123", after_event_id=0)
        self.assertEqual([event.event_id for event in replayed], [first.event_id, second.event_id])
        self.assertEqual(replayed[1].type, "node_added")

        after_first = self.store.list_events_after("gen_123", after_event_id=1)
        self.assertEqual(len(after_first), 1)
        self.assertEqual(after_first[0].event_id, 2)

    def test_active_generation_clears_after_completion(self) -> None:
        active = self.store.get_active_generation(user_id="user_123", video_id="video_123")
        self.assertIsNotNone(active)
        self.assertEqual(active.generation_id, self.metadata.generation_id)
        self.assertEqual(active.graph_id, "graph_123")

        completed = self.store.mark_completed("gen_123", payload={"node_count": 1, "edge_count": 0})
        self.assertEqual(completed.type, "completed")

        metadata = self.store.get_generation("gen_123")
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.status, IdeaGraphGenerationStatus.COMPLETED)
        self.assertIsNone(self.store.get_active_generation(user_id="user_123", video_id="video_123"))

    def test_terminal_generations_receive_ttl(self) -> None:
        self.store.mark_failed("gen_123", error="boom")

        meta_ttl = self.redis.ttl("idea_graph:generation:gen_123:meta")
        events_ttl = self.redis.ttl("idea_graph:generation:gen_123:events")
        self.assertGreater(meta_ttl, 0)
        self.assertGreater(events_ttl, 0)


if __name__ == "__main__":
    unittest.main()
