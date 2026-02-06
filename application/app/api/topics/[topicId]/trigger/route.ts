import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL;

interface RouteParams {
  params: Promise<{ topicId: string }>;
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

    const { topicId } = await params;

    // Verify ownership
    const existing = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    // Call the orchestrator trigger endpoint
    const response = await fetch(`${ORCHESTRATOR_URL}/trigger/${topicId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Orchestrator trigger failed:", errorText);
      return NextResponse.json(
        { error: "Failed to trigger pipeline" },
        { status: 502 },
      );
    }

    const result = await response.json();
    return NextResponse.json({
      success: true,
      message: "Pipeline triggered successfully",
      ...result,
    });
  } catch (error) {
    console.error("Error triggering pipeline:", error);
    return NextResponse.json(
      { error: "Failed to trigger pipeline. Is the orchestrator running?" },
      { status: 500 },
    );
  }
}
