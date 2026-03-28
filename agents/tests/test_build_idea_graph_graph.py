from __future__ import annotations

import unittest

from agents.idea_graph.build_idea_graph_graph import BuildIdeaGraphState, IdeaGraphContext


def _make_context() -> IdeaGraphContext:
    return IdeaGraphContext(
        BuildIdeaGraphState(
            user_id="user_123",
            video_id="video_123",
            video_title="Test video",
            transcript="One useful idea. Another supporting idea.",
        ),
        writer=None,
    )


class IdeaGraphContextIncrementalBuildTests(unittest.TestCase):
    def test_first_node_must_be_grounded_before_next_node(self) -> None:
        ctx = _make_context()

        first_node_id = ctx.add_node("CLAIM", "Main claim")

        with self.assertRaisesRegex(ValueError, "Finish the most recently added node"):
            ctx.add_node("EVIDENCE", "Ungrounded evidence")

        ctx.attach_source(
            node_id=first_node_id,
            quote="One useful idea.",
            start_sec=0,
            end_sec=5,
        )

        second_node_id = ctx.add_node("EVIDENCE", "Grounded follow-up")

        self.assertIsInstance(second_node_id, str)

    def test_new_node_with_existing_graph_must_get_source_and_edge(self) -> None:
        ctx = _make_context()

        root_node_id = ctx.add_node("CLAIM", "Root idea")
        ctx.attach_source(
            node_id=root_node_id,
            quote="One useful idea.",
            start_sec=0,
            end_sec=5,
        )

        child_node_id = ctx.add_node("EVIDENCE", "Supporting point")
        ctx.attach_source(
            node_id=child_node_id,
            quote="Another supporting idea.",
            start_sec=5,
            end_sec=10,
        )

        with self.assertRaisesRegex(ValueError, "Finish the most recently added node"):
            ctx.add_node("EXAMPLE", "Too early")

        ctx.add_edge(
            source_node_id=child_node_id,
            target_node_id=root_node_id,
            edge_type="SUPPORTS",
        )

        next_node_id = ctx.add_node("EXAMPLE", "Connected example")

        self.assertIsInstance(next_node_id, str)


if __name__ == "__main__":
    unittest.main()
