import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { IdeaGraphGenerationStatus } from "@/lib/generated/prisma/client";
import { prisma } from "@/lib/prisma";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL;

interface RouteParams {
  params: Promise<{ videoId: string }>;
}

interface OrchestratorGenerationResponse {
  generation_id: string;
  graph_id: string;
  user_id: string;
  video_id: string;
  status: string;
}

function buildEventsUrl(generationId: string) {
  return `${ORCHESTRATOR_URL}/idea-graphs/generations/${encodeURIComponent(generationId)}/events`;
}

export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    if (!ORCHESTRATOR_URL) {
      return NextResponse.json(
        { error: "ORCHESTRATOR_URL is not configured" },
        { status: 500 },
      );
    }

    const { videoId } = await params;
    const response = await fetch(
      `${ORCHESTRATOR_URL}/idea-graphs/generations/active?user_id=${encodeURIComponent(session.user.id)}&video_id=${encodeURIComponent(videoId)}`,
      {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Failed to fetch active idea graph generation:", errorText);
      return NextResponse.json(
        { error: "Failed to fetch active generation" },
        { status: 502 },
      );
    }

    const result = (await response.json().catch(() => null)) as {
      active?: boolean;
      generation?: OrchestratorGenerationResponse | null;
    } | null;

    if (!result?.active || !result.generation?.generation_id) {
      return NextResponse.json({
        active: false,
        generationId: null,
        graphId: null,
        eventsUrl: null,
        status: null,
      });
    }

    return NextResponse.json({
      active: true,
      generationId: result.generation.generation_id,
      graphId: result.generation.graph_id,
      status: result.generation.status,
      eventsUrl: buildEventsUrl(result.generation.generation_id),
    });
  } catch (error) {
    console.error("Error fetching active idea graph generation:", error);
    return NextResponse.json(
      { error: "Failed to fetch active generation" },
      { status: 500 },
    );
  }
}

export async function POST(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    if (!ORCHESTRATOR_URL) {
      return NextResponse.json(
        { error: "ORCHESTRATOR_URL is not configured" },
        { status: 500 },
      );
    }

    const { videoId } = await params;

    const video = await prisma.video.findUnique({
      where: { id: videoId },
      select: { id: true, transcript: true },
    });

    if (!video) {
      return NextResponse.json({ error: "Video not found" }, { status: 404 });
    }

    if (!video.transcript) {
      return NextResponse.json(
        { error: "No transcript available for this video" },
        { status: 400 },
      );
    }

    const existingGraph = await prisma.ideaGraph.findFirst({
      where: {
        userId: session.user.id,
        videoId,
      },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      select: {
        id: true,
        generationStatus: true,
        _count: {
          select: { nodes: true, edges: true },
        },
      },
    });

    if (
      existingGraph?.generationStatus === IdeaGraphGenerationStatus.GENERATING
    ) {
      return NextResponse.json(
        {
          error:
            "A generation is already in progress. Please wait for it to complete.",
        },
        { status: 409 },
      );
    }

    const createdGraph = await prisma.ideaGraph.create({
      data: {
        userId: session.user.id,
        videoId,
        generationStatus: IdeaGraphGenerationStatus.GENERATING,
      },
    });

    const response = await fetch(`${ORCHESTRATOR_URL}/idea-graphs/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        graph_id: createdGraph.id,
        user_id: session.user.id,
        video_id: videoId,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Orchestrator idea graph generation failed:", errorText);

      await prisma.ideaGraph.update({
        where: { id: createdGraph.id },
        data: {
          generationStatus: IdeaGraphGenerationStatus.FAILED,
          generationError: "Failed to start idea graph generation",
        },
      });

      return NextResponse.json(
        { error: "Failed to start idea graph generation" },
        { status: 502 },
      );
    }

    const result = (await response
      .json()
      .catch(() => null)) as OrchestratorGenerationResponse | null;
    if (!result?.generation_id) {
      await prisma.ideaGraph.update({
        where: { id: createdGraph.id },
        data: {
          generationStatus: IdeaGraphGenerationStatus.FAILED,
          generationError: "Invalid orchestrator response",
        },
      });
      return NextResponse.json(
        { error: "Invalid orchestrator response" },
        { status: 502 },
      );
    }

    return NextResponse.json({
      success: true,
      generationId: result.generation_id,
      graphId: result.graph_id,
      status: result.status,
      eventsUrl: buildEventsUrl(result.generation_id),
    });
  } catch (error) {
    console.error("Error triggering idea graph generation:", error);
    return NextResponse.json(
      { error: "Failed to start idea graph generation" },
      { status: 500 },
    );
  }
}
