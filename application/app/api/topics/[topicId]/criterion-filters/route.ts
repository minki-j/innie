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
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { topicId } = await params;

    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });
    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const filters = await prisma.criterionFilter.findMany({
      where: { topicId },
      include: {
        criterion: {
          select: { id: true, condition: true, topicId: true, include: true },
        },
      },
      orderBy: { createdAt: "asc" },
    });

    return NextResponse.json(filters);
  } catch (error) {
    console.error("Error fetching criterion filters:", error);
    return NextResponse.json({ error: "Failed to fetch criterion filters" }, { status: 500 });
  }
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { topicId } = await params;

    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });
    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    if (!topic.parentId) {
      return NextResponse.json(
        { error: "Cannot add criterion filters to a root topic" },
        { status: 400 },
      );
    }

    const body = await request.json();
    const { criterionId, requiredResult } = body;

    if (!criterionId || !requiredResult) {
      return NextResponse.json(
        { error: "criterionId and requiredResult are required" },
        { status: 400 },
      );
    }

    if (!["PASS", "FAIL", "CANNOT_TELL"].includes(requiredResult)) {
      return NextResponse.json({ error: "Invalid requiredResult value" }, { status: 400 });
    }

    // Verify criterion belongs to an ancestor topic owned by this user
    const criterion = await prisma.criterion.findUnique({
      where: { id: criterionId },
      include: { topic: { select: { userId: true } } },
    });

    if (!criterion || criterion.topic.userId !== session.user.id) {
      return NextResponse.json({ error: "Criterion not found" }, { status: 404 });
    }

    const filter = await prisma.criterionFilter.create({
      data: { topicId, criterionId, requiredResult },
      include: {
        criterion: { select: { id: true, condition: true, topicId: true, include: true } },
      },
    });

    return NextResponse.json(filter, { status: 201 });
  } catch (error: unknown) {
    if ((error as { code?: string }).code === "P2002") {
      return NextResponse.json(
        { error: "A filter for this criterion already exists" },
        { status: 409 },
      );
    }
    console.error("Error creating criterion filter:", error);
    return NextResponse.json({ error: "Failed to create criterion filter" }, { status: 500 });
  }
}
