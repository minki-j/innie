import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const topics = await prisma.topic.findMany({
      where: { userId: session.user.id },
      include: {
        _count: {
          select: {
            videos: true,
            criteria: true,
            criterionFilters: true,
            keywords: true,
            creators: true,
          },
        },
      },
      orderBy: { createdAt: "asc" },
    });

    return NextResponse.json(topics);
  } catch (error) {
    console.error("Error fetching topics:", error);
    return NextResponse.json(
      { error: "Failed to fetch topics" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const body = await request.json();
    const { name, description, parentId } = body;

    if (!name || typeof name !== "string" || name.trim().length === 0) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }

    // Validate parentId ownership if provided
    if (parentId) {
      const parent = await prisma.topic.findFirst({
        where: { id: parentId, userId: session.user.id },
      });
      if (!parent) {
        return NextResponse.json(
          { error: "Parent topic not found" },
          { status: 404 },
        );
      }
    }

    const topic = await prisma.topic.create({
      data: {
        name: name.trim(),
        description: description?.trim() || null,
        userId: session.user.id,
        ...(parentId && { parentId }),
      },
    });

    return NextResponse.json(topic, { status: 201 });
  } catch (error) {
    console.error("Error creating topic:", error);
    return NextResponse.json(
      { error: "Failed to create topic" },
      { status: 500 },
    );
  }
}
