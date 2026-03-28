import {
  IdeaGraphEdgeType,
  IdeaGraphGenerationStatus,
  IdeaGraphLayoutDirection,
  IdeaGraphNodeType,
  Prisma,
} from "@/lib/generated/prisma/client";

export const ideaGraphInclude = {
  nodes: {
    include: {
      transcriptSources: {
        orderBy: [{ startSec: "asc" }, { createdAt: "asc" }],
      },
    },
    orderBy: { createdAt: "asc" },
  },
  edges: {
    orderBy: { createdAt: "asc" },
  },
} satisfies Prisma.IdeaGraphInclude;

export type IdeaGraphWithRelations = Prisma.IdeaGraphGetPayload<{
  include: typeof ideaGraphInclude;
}>;

export interface IdeaGraphSourcePayload {
  id: string;
  paraphrase: string | null;
  quote: string;
  startSec: number;
  endSec: number;
}

export interface IdeaGraphNodePayload {
  id: string;
  type: IdeaGraphNodeType;
  title: string;
  content: string | null;
  x: number;
  y: number;
  collapsed: boolean;
  transcriptSources: IdeaGraphSourcePayload[];
}

export interface IdeaGraphEdgePayload {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  type: IdeaGraphEdgeType;
  label: string | null;
}

export interface IdeaGraphPayload {
  id: string;
  userId: string;
  videoId: string;
  generationStatus: IdeaGraphGenerationStatus;
  generationError: string | null;
  generatedAt: string | null;
  layoutDirection: IdeaGraphLayoutDirection;
  visibleDepth: number | null;
  createdAt: string;
  updatedAt: string;
  nodes: IdeaGraphNodePayload[];
  edges: IdeaGraphEdgePayload[];
}

export interface IdeaGraphSourceInput {
  id?: string;
  paraphrase?: string | null;
  quote: string;
  startSec: number;
  endSec: number;
}

export interface IdeaGraphNodeInput {
  id: string;
  type: IdeaGraphNodeType;
  title?: string;
  content?: string | null;
  x?: number;
  y?: number;
  collapsed?: boolean;
  transcriptSources?: IdeaGraphSourceInput[];
}

export interface IdeaGraphEdgeInput {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  type: IdeaGraphEdgeType;
  label?: string | null;
}

export function serializeIdeaGraph(graph: IdeaGraphWithRelations): IdeaGraphPayload {
  return {
    id: graph.id,
    userId: graph.userId,
    videoId: graph.videoId,
    generationStatus: graph.generationStatus,
    generationError: graph.generationError,
    generatedAt: graph.generatedAt?.toISOString() ?? null,
    layoutDirection: graph.layoutDirection,
    visibleDepth: graph.visibleDepth,
    createdAt: graph.createdAt.toISOString(),
    updatedAt: graph.updatedAt.toISOString(),
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      title: node.title,
      content: node.content,
      x: node.x,
      y: node.y,
      collapsed: node.collapsed,
      transcriptSources: node.transcriptSources.map((source) => ({
        id: source.id,
        paraphrase: source.paraphrase,
        quote: source.quote,
        startSec: source.startSec,
        endSec: source.endSec,
      })),
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      sourceNodeId: edge.sourceNodeId,
      targetNodeId: edge.targetNodeId,
      type: edge.type,
      label: edge.label,
    })),
  };
}
