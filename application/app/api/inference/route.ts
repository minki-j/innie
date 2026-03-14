import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

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
    const { modelName, funnelId, method, transcript, videoTitle } = body;

    if (!modelName && (!funnelId || !method)) {
      return NextResponse.json(
        {
          error:
            "Must provide either 'modelName' or both 'funnelId' and 'method'",
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
        funnelId: funnelId || undefined,
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
