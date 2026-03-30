import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import {
  IdeaGraphEdgeType,
  IdeaGraphGenerationStatus,
  IdeaGraphLayoutDirection,
  IdeaGraphNodeType,
} from "@/lib/generated/prisma/client";
import {
  ideaGraphInclude,
  ideaGraphVersionSelect,
  type IdeaGraphWithVersionsPayload,
  type IdeaGraphEdgeInput,
  type IdeaGraphNodeInput,
  serializeIdeaGraph,
  serializeIdeaGraphVersion,
} from "@/lib/idea-graph";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ videoId: string }>;
}

interface SaveIdeaGraphBody {
  nodes: IdeaGraphNodeInput[];
  edges: IdeaGraphEdgeInput[];
  layoutDirection?: IdeaGraphLayoutDirection;
  visibleDepth?: number | null;
}

interface UpdateIdeaGraphSettingsBody {
  layoutDirection?: IdeaGraphLayoutDirection;
  visibleDepth?: number | null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isIdeaGraphNodeType(value: unknown): value is IdeaGraphNodeType {
  return typeof value === "string" && Object.values(IdeaGraphNodeType).includes(value as IdeaGraphNodeType);
}

function isIdeaGraphEdgeType(value: unknown): value is IdeaGraphEdgeType {
  return typeof value === "string" && Object.values(IdeaGraphEdgeType).includes(value as IdeaGraphEdgeType);
}

function isIdeaGraphLayoutDirection(value: unknown): value is IdeaGraphLayoutDirection {
  return typeof value === "string" && Object.values(IdeaGraphLayoutDirection).includes(value as IdeaGraphLayoutDirection);
}

function validateNode(node: IdeaGraphNodeInput): string | null {
  if (!node.id || typeof node.id !== "string") return "Each node must include a string id";
  if (!isIdeaGraphNodeType(node.type)) return `Invalid node type for node ${node.id}`;
  if (node.title !== undefined && typeof node.title !== "string") return `Invalid title for node ${node.id}`;
  if (node.content !== undefined && node.content !== null && typeof node.content !== "string") {
    return `Invalid content for node ${node.id}`;
  }
  if (node.x !== undefined && !isFiniteNumber(node.x)) return `Invalid x position for node ${node.id}`;
  if (node.y !== undefined && !isFiniteNumber(node.y)) return `Invalid y position for node ${node.id}`;
  if (node.collapsed !== undefined && typeof node.collapsed !== "boolean") {
    return `Invalid collapsed state for node ${node.id}`;
  }

  for (const source of node.transcriptSources ?? []) {
    if (!source.quote || typeof source.quote !== "string") {
      return `Each transcript source on node ${node.id} must include a quote`;
    }
    if (source.paraphrase !== undefined && source.paraphrase !== null && typeof source.paraphrase !== "string") {
      return `Invalid source paraphrase on node ${node.id}`;
    }
    if (!isFiniteNumber(source.startSec) || !isFiniteNumber(source.endSec)) {
      return `Each transcript source on node ${node.id} must include numeric startSec and endSec`;
    }
    if (source.endSec < source.startSec) {
      return `Transcript source endSec must be greater than or equal to startSec on node ${node.id}`;
    }
  }

  return null;
}

function validateEdge(edge: IdeaGraphEdgeInput, nodeIds: Set<string>): string | null {
  if (!edge.id || typeof edge.id !== "string") return "Each edge must include a string id";
  if (!edge.sourceNodeId || typeof edge.sourceNodeId !== "string") {
    return `Each edge must include a sourceNodeId`;
  }
  if (!edge.targetNodeId || typeof edge.targetNodeId !== "string") {
    return `Each edge must include a targetNodeId`;
  }
  if (!nodeIds.has(edge.sourceNodeId) || !nodeIds.has(edge.targetNodeId)) {
    return `Edge ${edge.id} references a node that does not exist in this graph`;
  }
  if (!isIdeaGraphEdgeType(edge.type)) return `Invalid edge type for edge ${edge.id}`;
  if (edge.label !== undefined && edge.label !== null && typeof edge.label !== "string") {
    return `Invalid label for edge ${edge.id}`;
  }
  return null;
}

async function getGraphForUser(userId: string, videoId: string) {
  return prisma.ideaGraph.findFirst({
    where: {
      userId,
      videoId,
    },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    include: ideaGraphInclude,
  });
}

async function getGraphVersionsForUser(userId: string, videoId: string) {
  const versions = await prisma.ideaGraph.findMany({
    where: { userId, videoId },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    select: ideaGraphVersionSelect,
  });

  return versions.map(serializeIdeaGraphVersion);
}

async function getGraphByIdForUser(userId: string, videoId: string, graphId: string) {
  return prisma.ideaGraph.findFirst({
    where: {
      id: graphId,
      userId,
      videoId,
    },
    include: ideaGraphInclude,
  });
}

export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { videoId } = await params;
    const graphId = _request.nextUrl.searchParams.get("graphId");
    const includeVersions = _request.nextUrl.searchParams.get("includeVersions") === "true";
    const graph = graphId
      ? await getGraphByIdForUser(session.user.id, videoId, graphId)
      : await getGraphForUser(session.user.id, videoId);

    if (graphId && !graph) {
      return NextResponse.json({ error: "Idea graph version not found" }, { status: 404 });
    }

    if (includeVersions) {
      const payload: IdeaGraphWithVersionsPayload = {
        graph: graph ? serializeIdeaGraph(graph) : null,
        versions: await getGraphVersionsForUser(session.user.id, videoId),
      };

      return NextResponse.json(payload);
    }

    if (!graph) {
      return NextResponse.json(null);
    }

    return NextResponse.json(serializeIdeaGraph(graph));
  } catch (error) {
    console.error("Error fetching idea graph:", error);
    return NextResponse.json({ error: "Failed to fetch idea graph" }, { status: 500 });
  }
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { videoId } = await params;
    const graphId = request.nextUrl.searchParams.get("graphId");
    const body = (await request.json()) as SaveIdeaGraphBody;

    if (!Array.isArray(body.nodes) || !Array.isArray(body.edges)) {
      return NextResponse.json({ error: "nodes and edges arrays are required" }, { status: 400 });
    }
    if (body.layoutDirection !== undefined && !isIdeaGraphLayoutDirection(body.layoutDirection)) {
      return NextResponse.json({ error: "Invalid layoutDirection" }, { status: 400 });
    }
    if (
      body.visibleDepth !== undefined &&
      body.visibleDepth !== null &&
      (!Number.isInteger(body.visibleDepth) || body.visibleDepth < 0)
    ) {
      return NextResponse.json({ error: "visibleDepth must be a non-negative integer or null" }, { status: 400 });
    }

    const nodeIds = new Set<string>();
    for (const node of body.nodes) {
      const error = validateNode(node);
      if (error) {
        return NextResponse.json({ error }, { status: 400 });
      }
      if (nodeIds.has(node.id)) {
        return NextResponse.json({ error: `Duplicate node id: ${node.id}` }, { status: 400 });
      }
      nodeIds.add(node.id);
    }

    const edgeIds = new Set<string>();
    for (const edge of body.edges) {
      const error = validateEdge(edge, nodeIds);
      if (error) {
        return NextResponse.json({ error }, { status: 400 });
      }
      if (edgeIds.has(edge.id)) {
        return NextResponse.json({ error: `Duplicate edge id: ${edge.id}` }, { status: 400 });
      }
      edgeIds.add(edge.id);
    }

    const existingGraph = graphId
      ? await getGraphByIdForUser(session.user.id, videoId, graphId)
      : await getGraphForUser(session.user.id, videoId);

    if (graphId && !existingGraph) {
      return NextResponse.json({ error: "Idea graph version not found" }, { status: 404 });
    }

    const graph = await prisma.$transaction(async (tx) => {
      const current = existingGraph
        ? await tx.ideaGraph.update({
          where: { id: existingGraph.id },
          data: {
          generationStatus: IdeaGraphGenerationStatus.COMPLETED,
          generationError: null,
          generatedAt: new Date(),
          ...(body.layoutDirection !== undefined && { layoutDirection: body.layoutDirection }),
          ...(body.visibleDepth !== undefined && { visibleDepth: body.visibleDepth }),
          },
        })
        : await tx.ideaGraph.create({
          data: {
          userId: session.user.id,
          videoId,
          generationStatus: IdeaGraphGenerationStatus.COMPLETED,
          generatedAt: new Date(),
          layoutDirection: body.layoutDirection ?? IdeaGraphLayoutDirection.LR,
          visibleDepth: body.visibleDepth ?? null,
          },
        });

      await tx.ideaGraphEdge.deleteMany({ where: { graphId: current.id } });
      await tx.ideaGraphNode.deleteMany({ where: { graphId: current.id } });

      if (body.nodes.length > 0) {
        await tx.ideaGraphNode.createMany({
          data: body.nodes.map((node) => ({
            id: node.id,
            graphId: current.id,
            type: node.type,
            title: node.title ?? "",
            content: node.content ?? null,
            x: node.x ?? 0,
            y: node.y ?? 0,
            collapsed: node.collapsed ?? false,
          })),
        });
      }

      const sourceRows = body.nodes.flatMap((node) =>
        (node.transcriptSources ?? []).map((source) => ({
          id: source.id ?? crypto.randomUUID(),
          nodeId: node.id,
          paraphrase: source.paraphrase ?? null,
          quote: source.quote,
          startSec: source.startSec,
          endSec: source.endSec,
        }))
      );

      if (sourceRows.length > 0) {
        await tx.ideaGraphNodeSource.createMany({
          data: sourceRows,
        });
      }

      if (body.edges.length > 0) {
        await tx.ideaGraphEdge.createMany({
          data: body.edges.map((edge) => ({
            id: edge.id,
            graphId: current.id,
            sourceNodeId: edge.sourceNodeId,
            targetNodeId: edge.targetNodeId,
            type: edge.type,
            label: edge.label ?? null,
          })),
        });
      }

      return tx.ideaGraph.findUniqueOrThrow({
        where: { id: current.id },
        include: ideaGraphInclude,
      });
    }, {
      timeout: 20000,
    });

    return NextResponse.json(serializeIdeaGraph(graph));
  } catch (error) {
    console.error("Error saving idea graph:", error);
    return NextResponse.json({ error: "Failed to save idea graph" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { videoId } = await params;
    const graphId = request.nextUrl.searchParams.get("graphId");
    const body = (await request.json()) as UpdateIdeaGraphSettingsBody;

    if (body.layoutDirection !== undefined && !isIdeaGraphLayoutDirection(body.layoutDirection)) {
      return NextResponse.json({ error: "Invalid layoutDirection" }, { status: 400 });
    }
    if (
      body.visibleDepth !== undefined &&
      body.visibleDepth !== null &&
      (!Number.isInteger(body.visibleDepth) || body.visibleDepth < 0)
    ) {
      return NextResponse.json({ error: "visibleDepth must be a non-negative integer or null" }, { status: 400 });
    }

    const existingGraph = graphId
      ? await getGraphByIdForUser(session.user.id, videoId, graphId)
      : await getGraphForUser(session.user.id, videoId);

    if (graphId && !existingGraph) {
      return NextResponse.json({ error: "Idea graph version not found" }, { status: 404 });
    }

    const graph = existingGraph
      ? await prisma.ideaGraph.update({
      where: { id: existingGraph.id },
      data: {
        ...(body.layoutDirection !== undefined && { layoutDirection: body.layoutDirection }),
        ...(body.visibleDepth !== undefined && { visibleDepth: body.visibleDepth }),
      },
      include: ideaGraphInclude,
    })
      : await prisma.ideaGraph.create({
      data: {
        userId: session.user.id,
        videoId,
        layoutDirection: body.layoutDirection ?? IdeaGraphLayoutDirection.LR,
        visibleDepth: body.visibleDepth ?? null,
      },
      include: ideaGraphInclude,
    });

    return NextResponse.json(serializeIdeaGraph(graph));
  } catch (error) {
    console.error("Error updating idea graph settings:", error);
    return NextResponse.json({ error: "Failed to update idea graph settings" }, { status: 500 });
  }
}

export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { videoId } = await params;
    await prisma.ideaGraph.deleteMany({
      where: {
        userId: session.user.id,
        videoId,
      },
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting idea graph:", error);
    return NextResponse.json({ error: "Failed to delete idea graph" }, { status: 500 });
  }
}
