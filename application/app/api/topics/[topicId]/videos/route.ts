import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ topicId: string }>;
}

/**
 * GET /api/topics/[topicId]/videos
 * Returns all videos associated with a topic, including criteria scores.
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;

    // Verify topic ownership
    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
      select: { id: true },
    });

    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    // Fetch videos for this topic with criterion results
    const videos = await prisma.video.findMany({
      where: {
        topics: { some: { id: topicId } },
      },
      include: {
        criterionResults: {
          where: {
            criterion: { topicId, level: "MUST_HAVE" },
          },
          include: {
            criterion: {
              select: { include: true },
            },
          },
        },
      },
      orderBy: { updatedAt: "desc" },
    });

    // Transform to a simpler format with computed criteria scores
    const result = videos.map((v) => {
      let passed = 0;
      let total = 0;

      for (const cr of v.criterionResults) {
        total++;
        const include = cr.criterion.include;
        const result = cr.result;
        if (result === "CANNOT_TELL") continue;
        if (include ? result === "PASS" : result === "FAIL") {
          passed++;
        }
      }

      return {
        id: v.id,
        title: v.title,
        channelTitle: v.channelTitle,
        thumbnailMedium:
          v.thumbnailMedium ?? `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`,
        updatedAt: v.updatedAt.toISOString(),
        publishedAt: v.publishedAt.toISOString(),
        criteriaScore: total > 0 ? passed / total : null,
        passedCriteria: passed,
        totalCriteria: total,
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Error fetching topic videos:", error);
    return NextResponse.json(
      { error: "Failed to fetch videos" },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/topics/[topicId]/videos
 * Bulk disconnect videos from a topic (removes from the many-to-many relation).
 * Body: { videoIds: string[] }
 */
export async function DELETE(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;

    // Verify topic ownership
    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
      select: { id: true },
    });

    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const body = await request.json();
    const { videoIds } = body as { videoIds: string[] };

    if (!Array.isArray(videoIds) || videoIds.length === 0) {
      return NextResponse.json(
        { error: "videoIds array is required" },
        { status: 400 },
      );
    }

    // Disconnect videos from the topic
    await prisma.topic.update({
      where: { id: topicId },
      data: {
        videos: {
          disconnect: videoIds.map((id) => ({ id })),
        },
      },
    });

    // Also clean up criterion results for these videos under this topic
    await prisma.criterionResult.deleteMany({
      where: {
        videoId: { in: videoIds },
        criterion: { topicId },
      },
    });

    return NextResponse.json({
      success: true,
      removedCount: videoIds.length,
    });
  } catch (error) {
    console.error("Error removing videos from topic:", error);
    return NextResponse.json(
      { error: "Failed to remove videos" },
      { status: 500 },
    );
  }
}
