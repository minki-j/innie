import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ topicId: string }>;
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

    const { topicId } = await params;

    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
      include: {
        criteria: { orderBy: { order: "asc" } },
        criterionFilters: {
          include: { criterion: { select: { id: true, condition: true, topicId: true } } },
          orderBy: { createdAt: "asc" },
        },
        goldStandards: { orderBy: { createdAt: "desc" } },
        keywords: { orderBy: { createdAt: "desc" } },
        creators: { orderBy: { createdAt: "desc" } },
        children: {
          select: { id: true, name: true },
          orderBy: { createdAt: "asc" },
        },
        _count: { select: { videos: true, criteria: true, criterionFilters: true } },
      },
    });

    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    return NextResponse.json(topic);
  } catch (error) {
    console.error("Error fetching topic:", error);
    return NextResponse.json(
      { error: "Failed to fetch topic" },
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

    // Verify ownership
    const existing = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const body = await request.json();
    const { name, description, active, pipelineIntervalHours } = body;

    const topic = await prisma.topic.update({
      where: { id: topicId },
      data: {
        ...(name !== undefined && { name: name.trim() }),
        ...(description !== undefined && {
          description: description?.trim() || null,
        }),
        ...(active !== undefined && { active: Boolean(active) }),
        ...(pipelineIntervalHours !== undefined && {
          pipelineIntervalHours: Math.max(1, Math.min(168, Number(pipelineIntervalHours))),
        }),
      },
    });

    return NextResponse.json(topic);
  } catch (error) {
    console.error("Error updating topic:", error);
    return NextResponse.json(
      { error: "Failed to update topic" },
      { status: 500 },
    );
  }
}

export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { topicId } = await params;

    // Verify ownership
    const existing = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    await prisma.topic.delete({ where: { id: topicId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting topic:", error);
    return NextResponse.json(
      { error: "Failed to delete topic" },
      { status: 500 },
    );
  }
}
