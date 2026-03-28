# Idea Graph Implementation

This document summarizes the major implementation work for the video watch page idea graph feature.

It focuses on the main architecture, data model, backend flow, and editor behavior. Small UI polish changes made during iteration are intentionally omitted.

## Goal

Add a persisted, per-user idea graph to the video watch page that:

- generates from a video's title and transcript
- stores graph structure in the database
- supports editing in a canvas UI
- connects transcript evidence to graph nodes
- uses the `agents` repo for graph generation
- uses the `orchestrator` as the execution bridge between the application and LangGraph

## High-Level Architecture

The feature is split across three parts of the monorepo:

- `application`
  - renders the watch page
  - stores and edits graph state
  - triggers generation
- `orchestrator`
  - fetches transcript context
  - starts the LangGraph run
  - writes generated graph results back into the database
- `agents`
  - hosts the LangGraph graph-builder agent
  - reads transcript chunks and builds the idea graph

The flow is:

1. User opens a video watch page.
2. `application` fetches the current persisted graph for `userId + videoId`.
3. User clicks `Generate idea graph`.
4. `application` calls the orchestrator.
5. `orchestrator` prepares transcript context and current graph state.
6. `orchestrator` invokes the LangGraph assistant in `agents`.
7. The LangGraph agent returns a full graph snapshot.
8. `orchestrator` replaces the stored graph in Postgres.
9. `application` polls and re-renders the updated graph.

## Database Model

The graph is stored in Prisma under the `application` schema.

### Main tables

- `IdeaGraph`
  - one row per `userId + videoId`
  - stores generation state and graph-level view settings
- `IdeaGraphNode`
  - stores graph nodes
- `IdeaGraphEdge`
  - stores typed edges between nodes
- `IdeaGraphNodeSource`
  - stores transcript-backed evidence spans for a node

### Key fields

`IdeaGraph` stores:

- `generationStatus`
- `generationError`
- `generatedAt`
- `layoutDirection`
- `visibleDepth`

`IdeaGraphNode` stores:

- `type`
- `title`
- `content`
- `x`
- `y`
- `collapsed`

`IdeaGraphNodeSource` stores:

- `paraphrase`
- `quote`
- `startSec`
- `endSec`

This means both graph content and important graph-view state are now persisted in the DB.

## Application Layer

### Main watch page integration

The watch page now uses a client wrapper:

- `application/components/video/WatchPageClient.tsx`

This component is responsible for:

- rendering the main player and sidebar
- rendering the full-width idea graph section below the main content
- coordinating player seeking from graph interactions
- positioning the embedded floating mini-player inside the canvas area

### Idea graph editor

The core editor lives in:

- `application/components/video/IdeaGraphSection.tsx`

This component handles:

- fetching the graph
- polling during generation
- rendering the React Flow canvas
- persisting graph edits
- arranging with Dagre
- node selection and edge selection
- inspector editing
- graph depth filtering
- layout direction switching

### Player integration

The player wrapper lives in:

- `application/components/video/VideoPlayer.tsx`

It exposes:

- `seekTo(seconds)`

and supports:

- regular player mode
- embedded floating mini-player mode positioned by the graph canvas

### Application APIs

The main routes are:

- `application/app/api/videos/[videoId]/idea-graph/route.ts`
  - `GET`
    - fetch current graph
  - `PUT`
    - replace graph contents
  - `PATCH`
    - update view settings like layout direction and visible depth
  - `DELETE`
    - delete graph
- `application/app/api/videos/[videoId]/idea-graph/generate/route.ts`
  - starts background graph generation via the orchestrator

### Serialization

Shared API graph serialization lives in:

- `application/lib/idea-graph.ts`

This file defines the graph payload shape used by the frontend and routes.

## Orchestrator Layer

### Purpose

The orchestrator is the execution bridge. It is used instead of calling LangGraph directly from the browser or from the watch page UI.

This allows:

- background execution
- future buffering/retry behavior
- shared workflow handling in one backend layer

### Main files

- `orchestrator/flows/idea_graph.py`
  - main generation flow
- `orchestrator/server.py`
  - HTTP endpoint used by the application
- `orchestrator/tasks/db.py`
  - database read/write helpers for graph state
- `orchestrator/tasks/youtube.py`
  - transcript segment fetching for evidence grounding
- `orchestrator/models/schemas.py`
  - typed payloads for graph generation

### Main responsibilities

The orchestrator:

- loads current graph state
- loads transcript content
- tries to fetch timestamped transcript segments
- calls the LangGraph assistant
- validates the returned graph snapshot
- replaces the stored graph in Postgres
- updates generation status

## Agents Layer

### LangGraph registration

The new assistant is registered in:

- `agents/langgraph.json`

Registered graph name:

- `build_idea_graph`

### Main agent file

- `agents/agents/idea_graph/build_idea_graph_graph.py`

### Agent behavior

The agent is a graph-building workflow that:

- reads transcript chunks progressively
- inspects current graph state
- adds nodes and edges through tool calls
- attaches transcript-backed evidence spans
- returns a full `result_graph` snapshot

### Node and edge semantics

Supported node types include:

- `CLAIM`
- `EVIDENCE`
- `COUNTERARGUMENT`
- `REBUTTAL`
- `EXAMPLE`
- `ASSUMPTION`
- `DEFINITION`
- `QUESTION`
- `CONCLUSION`

Supported edge types include:

- `SUPPORTS`
- `ATTACKS`
- `REBUTS`
- `ELABORATES`
- `DEPENDS_ON`
- `ILLUSTRATES`
- `CONTRASTS_WITH`

## Graph Editing Behavior

The editor supports:

- selecting nodes and edges
- editing node title/content/type
- editing edge type/label
- adding transcript-backed sources
- creating connected child nodes from a node-end `+` action
- node collapse/expand
- dragging nodes
- arranging layout
- vertical and horizontal graph orientation
- visible depth filtering

### Dragging

Dragging behavior was updated to use live React Flow state, matching the funnel canvas behavior:

- local drag state updates while the mouse moves
- persistence still occurs after drag stop

## Layout and Arrange

Layout uses Dagre in:

- `application/components/video/IdeaGraphSection.tsx`

Current layout settings:

- `nodesep: 80`
- `ranksep: 130`

`Arrange` re-runs Dagre and persists the new node coordinates.

Changing vertical/horizontal layout also triggers an automatic arrange.

## Persisted View State

The following view settings are now stored in the DB on `IdeaGraph`:

- `layoutDirection`
- `visibleDepth`

This replaced the temporary local-storage implementation so those settings now follow the persisted graph instead of only the current browser.

## Save Strategy

Graph saves originally timed out on large graphs because node and edge rows were inserted one by one inside an interactive Prisma transaction.

This was changed to:

- batch node inserts with `createMany`
- batch source inserts with `createMany`
- batch edge inserts with `createMany`
- increase transaction timeout for headroom

This removed the `P2028` timeout failures seen while editing large generated graphs.

## Generation Robustness

Several fixes were added during implementation:

- explicit handling for missing/unauthenticated graph fetches
- orchestrator model generation fixed to ignore inline enum comments
- Redis config corrected for orchestrator rate limiting
- generation status transitions hardened so failures do not silently leave the graph stuck in `GENERATING`
- transcript chunking reduced and merged for long transcripts to avoid runaway tool-call behavior in the agent

## Testing and Verification

Validation performed during implementation included:

- Prisma migration + client generation
- Next.js production build
- targeted ESLint runs on edited files
- Python compile checks for orchestrator and agent modules
- orchestrator integration script:
  - `orchestrator/scripts/test_build_idea_graph.py`
- browser smoke testing on a real watch page

## Main Files Added or Changed

### Added

- `application/components/video/IdeaGraphSection.tsx`
- `application/components/video/WatchPageClient.tsx`
- `application/lib/idea-graph.ts`
- `application/app/api/videos/[videoId]/idea-graph/route.ts`
- `application/app/api/videos/[videoId]/idea-graph/generate/route.ts`
- `orchestrator/flows/idea_graph.py`
- `orchestrator/scripts/test_build_idea_graph.py`
- `agents/agents/idea_graph/build_idea_graph_graph.py`

### Updated

- `application/app/(main)/watch/[videoId]/page.tsx`
- `application/components/video/VideoPlayer.tsx`
- `application/prisma/schema.prisma`
- `orchestrator/server.py`
- `orchestrator/tasks/db.py`
- `orchestrator/tasks/youtube.py`
- `orchestrator/models/schemas.py`
- `agents/langgraph.json`

## Notes

This feature currently treats the graph as:

- private per user
- tied to a single video
- fully replaceable on regeneration
- fully editable after generation

The current implementation is a strong base for future additions like:

- incremental regeneration of a selected subgraph
- per-node comment threads
- richer mini-player interactions
- more advanced graph filters
