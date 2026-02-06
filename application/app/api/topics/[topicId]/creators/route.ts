import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ topicId: string }>;
}

async function verifyTopicOwnership(topicId: string, userId: string) {
  return prisma.topic.findFirst({
    where: { id: topicId, userId },
  });
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;
    if (!(await verifyTopicOwnership(topicId, session.user.id))) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const body = await request.json();
    const { channelId, channelUrl, channelName, scrapeMonthsBack = 1 } = body;

    if (!channelName && !channelUrl && !channelId) {
      return NextResponse.json(
        {
          error:
            "At least one of channelName, channelUrl, or channelId is required",
        },
        { status: 400 },
      );
    }

    const months = Math.min(Math.max(1, Number(scrapeMonthsBack) || 1), 12);

    const creator = await prisma.topicCreator.create({
      data: {
        topicId,
        channelId: channelId?.trim() || null,
        channelUrl: channelUrl?.trim() || null,
        channelName: channelName?.trim() || null,
        scrapeMonthsBack: months,
      },
    });

    return NextResponse.json(creator, { status: 201 });
  } catch (error) {
    console.error("Error creating creator:", error);
    return NextResponse.json(
      { error: "Failed to create creator" },
      { status: 500 },
    );
  }
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;
    if (!(await verifyTopicOwnership(topicId, session.user.id))) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const body = await request.json();
    const { id, channelId, channelUrl, channelName, scrapeMonthsBack } = body;

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    const data: Record<string, unknown> = {};
    if (channelId !== undefined) data.channelId = channelId?.trim() || null;
    if (channelUrl !== undefined) data.channelUrl = channelUrl?.trim() || null;
    if (channelName !== undefined)
      data.channelName = channelName?.trim() || null;
    if (scrapeMonthsBack !== undefined) {
      data.scrapeMonthsBack = Math.min(
        Math.max(1, Number(scrapeMonthsBack) || 1),
        12,
      );
    }

    const creator = await prisma.topicCreator.update({
      where: { id, topicId },
      data,
    });

    return NextResponse.json(creator);
  } catch (error) {
    console.error("Error updating creator:", error);
    return NextResponse.json(
      { error: "Failed to update creator" },
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

    const { topicId } = await params;
    if (!(await verifyTopicOwnership(topicId, session.user.id))) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const { searchParams } = request.nextUrl;
    const id = searchParams.get("id");

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    await prisma.topicCreator.delete({ where: { id, topicId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting creator:", error);
    return NextResponse.json(
      { error: "Failed to delete creator" },
      { status: 500 },
    );
  }
}
