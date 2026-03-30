---
name: Animate Idea Graph
overview: Add polished incremental animation to the idea graph canvas as streamed nodes and edges arrive. The default approach keeps the current React Flow + Dagre stack and adds lightweight position tweening plus enter animations instead of introducing a new motion dependency.
todos:
  - id: inspect-sync-points
    content: Map the current flowNodes/flowEdges sync points and add diff tracking for newly added nodes and edges.
    status: pending
  - id: animate-node-positions
    content: Introduce a lightweight interpolation loop for React Flow node positions during streamed generation updates.
    status: pending
  - id: animate-node-edge-entry
    content: Add entry animation styling for new nodes and new edges using component props plus global keyframes/CSS.
    status: pending
  - id: tune-viewport
    content: Adjust fitView timing so viewport motion complements the new graph animations instead of competing with them.
    status: pending
  - id: verify-streaming
    content: Manually verify streamed graph updates and run lint checks on the touched frontend files.
    status: pending
isProject: false
---

# Animate Idea Graph Updates

## Goal

Make streamed idea graph updates feel smooth by animating both:

- node position changes caused by repeated Dagre relayouts
- new node/edge appearance when SSE events add them

## Current Behavior

The jumpiness comes from two existing behaviors in [IdeaGraphSection.tsx](/Users/minkijung/Documents/SideProjects/innie/application/components/video/IdeaGraphSection.tsx):

- `displayedGraph` recomputes a full Dagre layout on every streamed update: `graph?.generationStatus === 'GENERATING' ? applyDagreLayout(graph, direction) : graph`
- React Flow state is then replaced immediately via `setCanvasNodes(flowNodes)` and `setCanvasEdges(flowEdges)`

That means nodes teleport to new coordinates and edges appear fully drawn in one frame.

## Proposed Implementation

Use the existing stack in [IdeaGraphSection.tsx](/Users/minkijung/Documents/SideProjects/innie/application/components/video/IdeaGraphSection.tsx), [idea-graph-stream.ts](/Users/minkijung/Documents/SideProjects/innie/application/lib/idea-graph-stream.ts), and [globals.css](/Users/minkijung/Documents/SideProjects/innie/application/app/globals.css) with no new dependency.

1. Add graph animation metadata in the UI layer

Keep short-lived refs/sets for:

- previous node positions by node id
- newly added node ids
- newly added edge ids

Populate those from diffs between the previous and next `flowNodes`/`flowEdges`, instead of changing the stream reducer shape unless needed.

1. Tween node movement between layouts

Replace the immediate `setCanvasNodes(flowNodes)` sync with a small animation loop that:

- starts from current rendered positions
- interpolates toward the latest Dagre positions over ~200-300ms
- preserves direct jumps for first render and non-generation cases

This work belongs near the existing `useNodesState` synchronization in [IdeaGraphSection.tsx](/Users/minkijung/Documents/SideProjects/innie/application/components/video/IdeaGraphSection.tsx).

1. Animate new node entry

Extend `IdeaGraphNodeCard` so newly added nodes get a brief enter treatment such as:

- fade in
- slight scale-up
- subtle lift/highlight

The animation class can be driven by `node.data` and implemented in [globals.css](/Users/minkijung/Documents/SideProjects/innie/application/app/globals.css) to keep the component simple.

1. Animate new edge drawing

Extend `WrappedEdge` so newly added edges animate their stroke on entry, likely via SVG dash offset or a short opacity + draw effect. This directly targets the current instant-pop path rendered by `BaseEdge`.

1. Make viewport motion cooperate with node motion

Tune the existing `fitView({ duration: 300 })` behavior so camera animation does not fight the node tween. Likely debounce or skip some `fitView` calls while a node transition is already running.

## Scope Notes

- Default approach: lightweight custom animation in the existing code.
- Avoid adding `framer-motion` unless the first pass feels insufficient.
- Avoid changing persisted graph data or backend event formats unless we discover the UI cannot reliably infer "new this tick" from diffs alone.

## Files Most Likely To Change

- [IdeaGraphSection.tsx](/Users/minkijung/Documents/SideProjects/innie/application/components/video/IdeaGraphSection.tsx)
- [globals.css](/Users/minkijung/Documents/SideProjects/innie/application/app/globals.css)
- Possibly [idea-graph-stream.ts](/Users/minkijung/Documents/SideProjects/innie/application/lib/idea-graph-stream.ts) only if event-derived animation flags are needed

## Verification

- Run the idea graph generation flow and watch several streamed updates.
- Confirm existing nodes glide to new positions instead of jumping.
- Confirm new nodes fade/scale in and new edges draw in instead of popping.
- Verify the viewport still follows growth without feeling jittery.
- Check lint errors for edited files after implementation.

