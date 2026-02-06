import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

/**
 * POST /api/training/[trainingRunId]/cancel
 *
 * Cancel a running training run.
 * Proxies to the lab server's POST /training/{trainingRunId}/cancel.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ trainingRunId: string }> },
) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { trainingRunId } = await params;

    // Verify the training run belongs to the authenticated user
    const trainingRun = await prisma.trainingRun.findFirst({
      where: { id: trainingRunId, userId: session.user.id },
    });

    if (!trainingRun) {
      return NextResponse.json(
        { error: "Training run not found" },
        { status: 404 },
      );
    }

    // Proxy cancel request to lab server
    const labResponse = await fetch(
      `${LAB_SERVER_URL}/training/${trainingRunId}/cancel`,
      { method: "POST" },
    );

    if (!labResponse.ok) {
      const error = await labResponse.json().catch(() => ({
        detail: "Unknown error from lab server",
      }));
      return NextResponse.json(
        { error: error.detail || "Failed to cancel training" },
        { status: labResponse.status },
      );
    }

    const result = await labResponse.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error cancelling training:", error);
    return NextResponse.json(
      { error: "Failed to cancel training" },
      { status: 500 },
    );
  }
}
