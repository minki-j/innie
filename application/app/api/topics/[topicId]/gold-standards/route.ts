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
    const { videoUrl, title, isPositive = true, note } = body;

    if (
      !videoUrl ||
      typeof videoUrl !== "string" ||
      videoUrl.trim().length === 0
    ) {
      return NextResponse.json(
        { error: "videoUrl is required" },
        { status: 400 },
      );
    }

    const goldStandard = await prisma.goldStandard.create({
      data: {
        topicId,
        videoUrl: videoUrl.trim(),
        title: title?.trim() || null,
        isPositive: Boolean(isPositive),
        note: note?.trim() || null,
      },
    });

    return NextResponse.json(goldStandard, { status: 201 });
  } catch (error) {
    console.error("Error creating gold standard:", error);
    return NextResponse.json(
      { error: "Failed to create gold standard" },
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
    const { id, videoUrl, title, isPositive, note } = body;

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    const goldStandard = await prisma.goldStandard.update({
      where: { id, topicId },
      data: {
        ...(videoUrl !== undefined && { videoUrl: videoUrl.trim() }),
        ...(title !== undefined && { title: title?.trim() || null }),
        ...(isPositive !== undefined && { isPositive: Boolean(isPositive) }),
        ...(note !== undefined && { note: note?.trim() || null }),
      },
    });

    return NextResponse.json(goldStandard);
  } catch (error) {
    console.error("Error updating gold standard:", error);
    return NextResponse.json(
      { error: "Failed to update gold standard" },
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

    await prisma.goldStandard.delete({ where: { id, topicId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting gold standard:", error);
    return NextResponse.json(
      { error: "Failed to delete gold standard" },
      { status: 500 },
    );
  }
}
