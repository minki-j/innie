import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

/**
 * GET /api/training/[trainingRunId]
 *
 * Get the status of a training run.
 * Proxies to the lab server's GET /training/{trainingRunId}.
 */
export async function GET(
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

    const labResponse = await fetch(
      `${LAB_SERVER_URL}/training/${trainingRunId}`,
      { method: "GET" },
    );

    if (!labResponse.ok) {
      const error = await labResponse.json().catch(() => ({
        detail: "Unknown error from lab server",
      }));
      return NextResponse.json(
        { error: error.detail || "Failed to fetch training status" },
        { status: labResponse.status },
      );
    }

    const result = await labResponse.json();

    // Verify the training run belongs to the authenticated user
    if (result.userId !== session.user.id) {
      return NextResponse.json(
        { error: "Not authorized to view this training run" },
        { status: 403 },
      );
    }

    return NextResponse.json(result);
  } catch (error) {
    console.error("Error fetching training status:", error);
    return NextResponse.json(
      { error: "Failed to fetch training status" },
      { status: 500 },
    );
  }
}
