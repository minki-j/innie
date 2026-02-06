import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

/**
 * POST /api/inference
 *
 * Generate a review using a trained innie model.
 * Proxies to the lab server's POST /inference.
 */
export async function POST(request: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const body = await request.json();
    const { modelName, topicId, method, transcript, videoTitle } = body;

    // Must provide either modelName or (topicId + method)
    if (!modelName && (!topicId || !method)) {
      return NextResponse.json(
        {
          error:
            "Must provide either 'modelName' or both 'topicId' and 'method'",
        },
        { status: 400 },
      );
    }

    if (!transcript) {
      return NextResponse.json(
        { error: "transcript is required" },
        { status: 400 },
      );
    }

    const labResponse = await fetch(`${LAB_SERVER_URL}/inference`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        modelName: modelName || undefined,
        topicId: topicId || undefined,
        method: method || undefined,
        transcript,
        videoTitle: videoTitle || undefined,
      }),
    });

    if (!labResponse.ok) {
      const error = await labResponse.json().catch(() => ({
        detail: "Unknown error from lab server",
      }));
      return NextResponse.json(
        { error: error.detail || "Inference request failed" },
        { status: labResponse.status },
      );
    }

    const result = await labResponse.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error running inference:", error);
    return NextResponse.json(
      { error: "Failed to run inference" },
      { status: 500 },
    );
  }
}
