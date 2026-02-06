import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

/**
 * POST /api/training
 *
 * Trigger a new training run for the authenticated user's topic.
 * Proxies to the lab server's POST /training/start.
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
    const { topicId, method } = body;

    if (!topicId || !method) {
      return NextResponse.json(
        { error: "topicId and method are required" },
        { status: 400 },
      );
    }

    if (!["SFT", "RLVR"].includes(method)) {
      return NextResponse.json(
        { error: "method must be 'SFT' or 'RLVR'" },
        { status: 400 },
      );
    }

    // Build the webhook URL pointing back to this app
    const appUrl = process.env.NEXTAUTH_URL || request.nextUrl.origin;
    const webhookUrl = `${appUrl}/api/webhooks/training`;

    const labResponse = await fetch(`${LAB_SERVER_URL}/training/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: session.user.id,
        topicId,
        method,
        webhookUrl,
        config: body.config || null,
      }),
    });

    if (!labResponse.ok) {
      const error = await labResponse.json().catch(() => ({
        detail: "Unknown error from lab server",
      }));
      return NextResponse.json(
        { error: error.detail || "Training request failed" },
        { status: labResponse.status },
      );
    }

    const result = await labResponse.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error starting training:", error);
    return NextResponse.json(
      { error: "Failed to start training" },
      { status: 500 },
    );
  }
}
