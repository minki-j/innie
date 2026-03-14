import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const LAB_SERVER_URL = process.env.LAB_SERVER_URL || "http://localhost:8100";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ videoId: string }> },
) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { videoId } = await params;
    const { funnelId } = await request.json();

    if (!funnelId) {
      return NextResponse.json(
        { error: "funnelId is required" },
        { status: 400 },
      );
    }

    const video = await prisma.video.findUnique({
      where: { id: videoId },
      select: { title: true, transcript: true },
    });

    if (!video) {
      return NextResponse.json(
        { error: "Video not found" },
        { status: 404 },
      );
    }

    if (!video.transcript) {
      return NextResponse.json(
        { error: "No transcript available for this video" },
        { status: 400 },
      );
    }

    let labResponse: Response | null = null;
    for (const method of ["RLVR", "SFT"]) {
      labResponse = await fetch(`${LAB_SERVER_URL}/inference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          funnelId,
          method,
          transcript: video.transcript,
          videoTitle: video.title,
        }),
      });
      if (labResponse.ok) break;
    }

    if (!labResponse || !labResponse.ok) {
      const error = await labResponse
        ?.json()
        .catch(() => ({ detail: "No trained model available" }));
      return NextResponse.json(
        {
          error:
            error?.detail || "No trained model available for this funnel",
        },
        { status: labResponse?.status ?? 500 },
      );
    }

    const result = await labResponse.json();
    const reviewText: string = result.review;

    const encoder = new TextEncoder();
    const words = reviewText.split(/(\s+)/);

    const stream = new ReadableStream({
      async start(controller) {
        for (const word of words) {
          controller.enqueue(encoder.encode(word));
          if (word.trim()) {
            await new Promise((resolve) => setTimeout(resolve, 30));
          }
        }
        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
      },
    });
  } catch (error) {
    console.error("Error generating innie review:", error);
    return NextResponse.json(
      { error: "Failed to generate review" },
      { status: 500 },
    );
  }
}
