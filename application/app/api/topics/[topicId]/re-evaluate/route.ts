import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL;

interface RouteParams {
  params: Promise<{ topicId: string }>;
}

/**
 * POST /api/topics/[topicId]/re-evaluate
 * Re-evaluate selected videos against the topic's current criteria.
 * Body: { videoIds: string[] }
 */
export async function POST(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;

    // Verify ownership
    const existing = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const body = await request.json();
    const { videoIds } = body as { videoIds: string[] };

    if (!Array.isArray(videoIds) || videoIds.length === 0) {
      return NextResponse.json(
        { error: "videoIds array is required" },
        { status: 400 },
      );
    }

    // Call the orchestrator re-evaluate endpoint
    const response = await fetch(`${ORCHESTRATOR_URL}/re-evaluate/${topicId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_ids: videoIds }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Orchestrator re-evaluate failed:", errorText);
      return NextResponse.json(
        { error: "Failed to start re-evaluation" },
        { status: 502 },
      );
    }

    const result = await response.json();
    return NextResponse.json({
      success: true,
      message: "Re-evaluation started successfully",
      ...result,
    });
  } catch (error) {
    console.error("Error triggering re-evaluation:", error);
    return NextResponse.json(
      {
        error: "Failed to start re-evaluation. Is the orchestrator running?",
      },
      { status: 500 },
    );
  }
}
