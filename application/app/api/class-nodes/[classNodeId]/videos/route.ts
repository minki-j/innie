import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ classNodeId: string }>;
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

    const { classNodeId } = await params;

    const classNode = await prisma.classNode.findFirst({
      where: { id: classNodeId, funnel: { userId: session.user.id } },
    });
    if (!classNode) {
      return NextResponse.json(
        { error: "Class node not found" },
        { status: 404 },
      );
    }

    const results = await prisma.classNodeResult.findMany({
      where: { classNodeId, result: "PASS" },
      include: {
        video: {
          select: {
            id: true,
            title: true,
            channelTitle: true,
            thumbnailMedium: true,
            publishedAt: true,
          },
        },
      },
      orderBy: { createdAt: "desc" },
    });

    const videos = results.map((r) => ({
      id: r.video.id,
      title: r.video.title,
      channelTitle: r.video.channelTitle,
      thumbnailMedium:
        r.video.thumbnailMedium ??
        `https://i.ytimg.com/vi/${r.video.id}/mqdefault.jpg`,
      publishedAt: r.video.publishedAt.toISOString(),
      confidence: r.confidence,
      explanation: r.explanation,
    }));

    return NextResponse.json(videos);
  } catch (error) {
    console.error("Error fetching class node videos:", error);
    return NextResponse.json(
      { error: "Failed to fetch videos" },
      { status: 500 },
    );
  }
}
