import test from "node:test";
import assert from "node:assert/strict";

import { applyIdeaGraphStreamEvent, type IdeaGraphStreamEvent } from "./idea-graph-stream";

function makeEvent(
  type: IdeaGraphStreamEvent["type"],
  payload: Record<string, unknown>,
  eventId: number
): IdeaGraphStreamEvent {
  return {
    generation_id: "gen_123",
    event_id: eventId,
    user_id: "user_123",
    video_id: "video_123",
    timestamp: new Date(`2026-03-28T12:00:0${eventId}Z`).toISOString(),
    type,
    payload,
  };
}

test("applyIdeaGraphStreamEvent rebuilds graph from streamed events", () => {
  let graph = applyIdeaGraphStreamEvent(
    null,
    makeEvent("generation_started", {}, 1)
  );

  graph = applyIdeaGraphStreamEvent(
    graph,
    makeEvent(
      "node_added",
      {
        node: {
          id: "node_a",
          type: "CLAIM",
          title: "Remote work needs writing",
          content: "Main claim",
          x: 0,
          y: 0,
          collapsed: false,
          transcriptSources: [],
        },
      },
      2
    )
  );

  graph = applyIdeaGraphStreamEvent(
    graph,
    makeEvent(
      "source_attached",
      {
        nodeId: "node_a",
        source: {
          id: "source_a",
          paraphrase: "Docs preserve decisions",
          quote: "written decision log",
          startSec: 12,
          endSec: 18,
        },
      },
      3
    )
  );

  graph = applyIdeaGraphStreamEvent(
    graph,
    makeEvent(
      "node_added",
      {
        node: {
          id: "node_b",
          type: "EVIDENCE",
          title: "Product team example",
          content: null,
          x: 0,
          y: 0,
          collapsed: false,
          transcriptSources: [],
        },
      },
      4
    )
  );

  graph = applyIdeaGraphStreamEvent(
    graph,
    makeEvent(
      "edge_added",
      {
        edge: {
          id: "edge_a",
          sourceNodeId: "node_b",
          targetNodeId: "node_a",
          type: "SUPPORTS",
          label: null,
        },
      },
      5
    )
  );

  assert.ok(graph);
  assert.equal(graph.generationStatus, "GENERATING");
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.edges.length, 1);
  assert.equal(graph.nodes[0].transcriptSources.length, 1);
  assert.equal(graph.nodes[0].transcriptSources[0].quote, "written decision log");
});

test("applyIdeaGraphStreamEvent marks completion and failure states", () => {
  const baseGraph = applyIdeaGraphStreamEvent(
    null,
    makeEvent("generation_started", {}, 1)
  );

  const completedGraph = applyIdeaGraphStreamEvent(baseGraph, makeEvent("completed", {}, 2));
  assert.ok(completedGraph);
  assert.equal(completedGraph.generationStatus, "COMPLETED");

  const failedGraph = applyIdeaGraphStreamEvent(
    baseGraph,
    makeEvent("failed", { error: "Agent crashed" }, 3)
  );
  assert.ok(failedGraph);
  assert.equal(failedGraph.generationStatus, "FAILED");
  assert.equal(failedGraph.generationError, "Agent crashed");
});

test("generation_started replaces an existing graph with the streamed snapshot", () => {
  const existingGraph = {
    id: "graph_123",
    userId: "user_123",
    videoId: "video_123",
    generationStatus: "COMPLETED" as const,
    generationError: null,
    generatedAt: null,
    layoutDirection: "LR" as const,
    visibleDepth: null,
    createdAt: new Date("2026-03-28T11:59:59Z").toISOString(),
    updatedAt: new Date("2026-03-28T11:59:59Z").toISOString(),
    nodes: [
      {
        id: "old_node",
        type: "CLAIM" as const,
        title: "Old node",
        content: null,
        x: 10,
        y: 20,
        collapsed: false,
        transcriptSources: [],
      },
    ],
    edges: [
      {
        id: "old_edge",
        sourceNodeId: "old_node",
        targetNodeId: "old_node",
        type: "SUPPORTS" as const,
        label: null,
      },
    ],
  };

  const nextGraph = applyIdeaGraphStreamEvent(
    existingGraph,
    makeEvent("generation_started", {}, 1)
  );

  assert.ok(nextGraph);
  assert.equal(nextGraph.generationStatus, "GENERATING");
  assert.deepEqual(nextGraph.nodes, []);
  assert.deepEqual(nextGraph.edges, []);
});
