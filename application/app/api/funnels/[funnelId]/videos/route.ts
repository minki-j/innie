import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ funnelId: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { funnelId } = await params;

    const funnel = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
      select: { id: true },
    });

    if (!funnel) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const videos = await prisma.video.findMany({
      where: {
        funnelVideos: { some: { funnelId } },
      },
      include: {
        funnelVideos: {
          where: { funnelId },
          select: { updatedAt: true },
        },
        classNodeResults: {
          where: {
            classNode: { funnelId },
          },
        },
      },
      orderBy: { updatedAt: "desc" },
    });

    const result = videos.map((v) => {
      const passed = v.classNodeResults.filter((r) => r.result === "PASS").length;
      const total = v.classNodeResults.length;
      const processedAt = v.funnelVideos[0]?.updatedAt ?? v.updatedAt;

      return {
        id: v.id,
        title: v.title,
        channelTitle: v.channelTitle,
        thumbnailMedium:
          v.thumbnailMedium ?? `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`,
        updatedAt: processedAt.toISOString(),
        publishedAt: v.publishedAt.toISOString(),
        classNodeScore: total > 0 ? passed / total : null,
        passedNodes: passed,
        totalNodes: total,
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Error fetching funnel videos:", error);
    return NextResponse.json(
      { error: "Failed to fetch videos" },
      { status: 500 },
    );
  }
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { funnelId } = await params;

    const funnel = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
      select: { id: true },
    });

    if (!funnel) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const body = await request.json();
    const { videoIds } = body as { videoIds: string[] };

    if (!Array.isArray(videoIds) || videoIds.length === 0) {
      return NextResponse.json(
        { error: "videoIds array is required" },
        { status: 400 },
      );
    }

    await prisma.funnelVideo.deleteMany({
      where: {
        funnelId,
        videoId: { in: videoIds },
      },
    });

    // Clean up class node results for these videos under this funnel
    await prisma.classNodeResult.deleteMany({
      where: {
        videoId: { in: videoIds },
        classNode: { funnelId },
      },
    });

    return NextResponse.json({
      success: true,
      removedCount: videoIds.length,
    });
  } catch (error) {
    console.error("Error removing videos from funnel:", error);
    return NextResponse.json(
      { error: "Failed to remove videos" },
      { status: 500 },
    );
  }
}
