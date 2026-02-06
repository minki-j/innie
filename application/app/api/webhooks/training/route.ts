import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/webhooks/training
 *
 * Receives webhook notifications from the lab server when
 * training completes or fails.
 *
 * Payload shape:
 * {
 *   event: "training.completed" | "training.failed",
 *   trainingRunId: string,
 *   modelName: string,
 *   status: "COMPLETED" | "FAILED",
 *   userId: string,
 *   topicId: string,
 *   method: "SFT" | "RLVR",
 *   metrics?: { ... },
 *   error?: string,
 *   completedAt?: string,
 * }
 */
export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();

    const {
      event,
      trainingRunId,
      modelName,
      status,
      userId,
      topicId,
      method,
      metrics,
      error: errorMsg,
    } = payload;

    console.log(
      `[Training Webhook] event=${event} run=${trainingRunId} model=${modelName} status=${status} user=${userId} topic=${topicId} method=${method}`,
    );

    if (status === "COMPLETED") {
      console.log(
        `[Training Webhook] Training completed successfully. Metrics:`,
        metrics,
      );
      // TODO: Send notification to user (email, in-app notification, etc.)
      // TODO: Update any UI-relevant state
    } else if (status === "FAILED") {
      console.error(`[Training Webhook] Training failed. Error: ${errorMsg}`);
      // TODO: Notify user of failure
    } else if (status === "CANCELLED") {
      console.log(`[Training Webhook] Training cancelled by user.`);
    }

    return NextResponse.json({ received: true });
  } catch (error) {
    console.error("Error processing training webhook:", error);
    return NextResponse.json(
      { error: "Failed to process webhook" },
      { status: 500 },
    );
  }
}
