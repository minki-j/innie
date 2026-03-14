import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prefect } from "@/lib/prefect";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ funnelId: string }>;
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

    const { funnelId } = await params;

    const existing = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const flowRun = await prefect.createFlowRun(
      "video_pipeline",
      "video-pipeline",
      { funnel_id: funnelId },
    );

    return NextResponse.json({
      success: true,
      message: "Pipeline triggered successfully",
      flowRunId: flowRun.id,
      state: flowRun.state.type,
    });
  } catch (error) {
    console.error("Error triggering pipeline:", error);
    return NextResponse.json(
      { error: "Failed to trigger pipeline" },
      { status: 500 },
    );
  }
}
