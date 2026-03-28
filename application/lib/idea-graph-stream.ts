import { type IdeaGraphPayload, type IdeaGraphEdgePayload, type IdeaGraphNodePayload } from "./idea-graph";

export type IdeaGraphStreamEventType =
  | "generation_started"
  | "chunk_index_ready"
  | "chunk_read"
  | "node_added"
  | "node_updated"
  | "edge_added"
  | "source_attached"
  | "snapshot"
  | "completed"
  | "failed";

export interface IdeaGraphStreamEvent {
  generation_id: string;
  event_id: number;
  user_id: string;
  video_id: string;
  timestamp: string;
  type: IdeaGraphStreamEventType;
  payload: Record<string, unknown>;
}

export interface StartIdeaGraphGenerationResponse {
  success: boolean;
  generationId: string;
  status: string;
  eventsUrl: string;
}

export interface ActiveIdeaGraphGenerationResponse {
  active: boolean;
  generationId: string | null;
  status: string | null;
  eventsUrl: string | null;
}

type IdeaGraphSnapshotPayload = Pick<IdeaGraphPayload, "nodes" | "edges">;

function buildBaseGraph(graph: IdeaGraphPayload | null): IdeaGraphPayload {
  const now = new Date().toISOString();
  return (
    graph ?? {
      id: "",
      userId: "",
      videoId: "",
      generationStatus: "GENERATING",
      generationError: null,
      generatedAt: null,
      layoutDirection: "LR",
      visibleDepth: null,
      createdAt: now,
      updatedAt: now,
      nodes: [],
      edges: [],
    }
  );
}

function applySnapshot(
  graph: IdeaGraphPayload | null,
  snapshot: IdeaGraphSnapshotPayload
): IdeaGraphPayload {
  const base = buildBaseGraph(graph);
  return {
    ...base,
    generationStatus: "GENERATING",
    generationError: null,
    updatedAt: new Date().toISOString(),
    nodes: snapshot.nodes.map((node) => ({ ...node })),
    edges: snapshot.edges.map((edge) => ({ ...edge })),
  };
}

function upsertNode(nodes: IdeaGraphNodePayload[], nextNode: IdeaGraphNodePayload): IdeaGraphNodePayload[] {
  const existingIndex = nodes.findIndex((node) => node.id === nextNode.id);
  if (existingIndex === -1) {
    return [...nodes, nextNode];
  }
  return nodes.map((node, index) => (index === existingIndex ? nextNode : node));
}

function upsertEdge(edges: IdeaGraphEdgePayload[], nextEdge: IdeaGraphEdgePayload): IdeaGraphEdgePayload[] {
  const existingIndex = edges.findIndex((edge) => edge.id === nextEdge.id);
  if (existingIndex === -1) {
    return [...edges, nextEdge];
  }
  return edges.map((edge, index) => (index === existingIndex ? nextEdge : edge));
}

export function applyIdeaGraphStreamEvent(
  graph: IdeaGraphPayload | null,
  event: IdeaGraphStreamEvent
): IdeaGraphPayload | null {
  const base = buildBaseGraph(graph);

  switch (event.type) {
    case "generation_started": {
      const snapshot = event.payload.initial_graph as IdeaGraphSnapshotPayload | undefined;
      return applySnapshot(base, snapshot ?? { nodes: [], edges: [] });
    }
    case "snapshot": {
      const snapshot = event.payload.graph as IdeaGraphSnapshotPayload | undefined;
      if (!snapshot) return base;
      return applySnapshot(base, snapshot);
    }
    case "node_added":
    case "node_updated": {
      const node = event.payload.node as IdeaGraphNodePayload | undefined;
      if (!node) return base;
      return {
        ...base,
        generationStatus: "GENERATING",
        generationError: null,
        updatedAt: event.timestamp,
        nodes: upsertNode(base.nodes, node),
      };
    }
    case "edge_added": {
      const edge = event.payload.edge as IdeaGraphEdgePayload | undefined;
      if (!edge) return base;
      return {
        ...base,
        generationStatus: "GENERATING",
        generationError: null,
        updatedAt: event.timestamp,
        edges: upsertEdge(base.edges, edge),
      };
    }
    case "source_attached": {
      const nodeId = event.payload.nodeId as string | undefined;
      const source = event.payload.source as IdeaGraphNodePayload["transcriptSources"][number] | undefined;
      if (!nodeId || !source) return base;
      return {
        ...base,
        generationStatus: "GENERATING",
        generationError: null,
        updatedAt: event.timestamp,
        nodes: base.nodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                transcriptSources: node.transcriptSources.some((candidate) => candidate.id === source.id)
                  ? node.transcriptSources.map((candidate) => (candidate.id === source.id ? source : candidate))
                  : [...node.transcriptSources, source],
              }
            : node
        ),
      };
    }
    case "completed":
      return {
        ...base,
        generationStatus: "COMPLETED",
        generationError: null,
        updatedAt: event.timestamp,
      };
    case "failed":
      return {
        ...base,
        generationStatus: "FAILED",
        generationError: typeof event.payload.error === "string" ? event.payload.error : "Idea graph generation failed.",
        updatedAt: event.timestamp,
      };
    case "chunk_index_ready":
    case "chunk_read":
      return {
        ...base,
        generationStatus: "GENERATING",
        generationError: null,
        updatedAt: event.timestamp,
      };
    default:
      return base;
  }
}
