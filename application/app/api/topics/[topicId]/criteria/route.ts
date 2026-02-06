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
    const { condition, include = true, level = "MUST_HAVE" } = body;

    if (
      !condition ||
      typeof condition !== "string" ||
      condition.trim().length === 0
    ) {
      return NextResponse.json(
        { error: "condition is required" },
        { status: 400 },
      );
    }

    if (!["MUST_HAVE", "NICE_TO_HAVE"].includes(level)) {
      return NextResponse.json(
        { error: "level must be MUST_HAVE or NICE_TO_HAVE" },
        { status: 400 },
      );
    }

    // Get max order for this topic
    const maxOrder = await prisma.criterion.aggregate({
      where: { topicId },
      _max: { order: true },
    });

    const criterion = await prisma.criterion.create({
      data: {
        topicId,
        condition: condition.trim(),
        include: Boolean(include),
        level,
        order: (maxOrder._max.order ?? -1) + 1,
      },
    });

    return NextResponse.json(criterion, { status: 201 });
  } catch (error) {
    console.error("Error creating criterion:", error);
    return NextResponse.json(
      { error: "Failed to create criterion" },
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
    const { id, condition, include, level, order } = body;

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    if (level !== undefined && !["MUST_HAVE", "NICE_TO_HAVE"].includes(level)) {
      return NextResponse.json(
        { error: "level must be MUST_HAVE or NICE_TO_HAVE" },
        { status: 400 },
      );
    }

    const criterion = await prisma.criterion.update({
      where: { id, topicId },
      data: {
        ...(condition !== undefined && { condition: condition.trim() }),
        ...(include !== undefined && { include: Boolean(include) }),
        ...(level !== undefined && { level }),
        ...(order !== undefined && { order }),
      },
    });

    return NextResponse.json(criterion);
  } catch (error) {
    console.error("Error updating criterion:", error);
    return NextResponse.json(
      { error: "Failed to update criterion" },
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

    await prisma.criterion.delete({ where: { id, topicId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting criterion:", error);
    return NextResponse.json(
      { error: "Failed to delete criterion" },
      { status: 500 },
    );
  }
}
