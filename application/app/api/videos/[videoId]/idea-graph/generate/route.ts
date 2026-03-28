import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { IdeaGraphGenerationStatus } from "@/lib/generated/prisma/client";
import { prisma } from "@/lib/prisma";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL;

interface RouteParams {
  params: Promise<{ videoId: string }>;
}

interface GenerateIdeaGraphBody {
  replaceExisting?: boolean;
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    if (!ORCHESTRATOR_URL) {
      return NextResponse.json({ error: "ORCHESTRATOR_URL is not configured" }, { status: 500 });
    }

    const { videoId } = await params;
    const body = (await request.json().catch(() => ({}))) as GenerateIdeaGraphBody;
    const replaceExisting = body.replaceExisting === true;

    const video = await prisma.video.findUnique({
      where: { id: videoId },
      select: { id: true, transcript: true },
    });

    if (!video) {
      return NextResponse.json({ error: "Video not found" }, { status: 404 });
    }

    if (!video.transcript) {
      return NextResponse.json({ error: "No transcript available for this video" }, { status: 400 });
    }

    const existingGraph = await prisma.ideaGraph.findUnique({
      where: {
        userId_videoId: {
          userId: session.user.id,
          videoId,
        },
      },
      select: {
        id: true,
        generationStatus: true,
        _count: {
          select: { nodes: true, edges: true },
        },
      },
    });

    const hasExistingGraph = !!existingGraph && (existingGraph._count.nodes > 0 || existingGraph._count.edges > 0);
    if (hasExistingGraph && !replaceExisting) {
      return NextResponse.json(
        {
          error: "Graph already exists and would be replaced",
          requiresConfirmation: true,
        },
        { status: 409 },
      );
    }

    await prisma.ideaGraph.upsert({
      where: {
        userId_videoId: {
          userId: session.user.id,
          videoId,
        },
      },
      update: {
        generationStatus: IdeaGraphGenerationStatus.GENERATING,
        generationError: null,
      },
      create: {
        userId: session.user.id,
        videoId,
        generationStatus: IdeaGraphGenerationStatus.GENERATING,
      },
    });

    const response = await fetch(`${ORCHESTRATOR_URL}/idea-graphs/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: session.user.id,
        video_id: videoId,
        replace_existing: replaceExisting,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Orchestrator idea graph generation failed:", errorText);

      await prisma.ideaGraph.update({
        where: {
          userId_videoId: {
            userId: session.user.id,
            videoId,
          },
        },
        data: {
          generationStatus: IdeaGraphGenerationStatus.FAILED,
          generationError: "Failed to start idea graph generation",
        },
      });

      return NextResponse.json({ error: "Failed to start idea graph generation" }, { status: 502 });
    }

    const result = await response.json();
    return NextResponse.json({
      success: true,
      message: "Idea graph generation started successfully",
      ...result,
    });
  } catch (error) {
    console.error("Error triggering idea graph generation:", error);
    return NextResponse.json({ error: "Failed to start idea graph generation" }, { status: 500 });
  }
}
