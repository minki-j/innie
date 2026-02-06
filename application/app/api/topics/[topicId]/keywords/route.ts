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
    const { keyword } = body;

    if (
      !keyword ||
      typeof keyword !== "string" ||
      keyword.trim().length === 0
    ) {
      return NextResponse.json(
        { error: "keyword is required" },
        { status: 400 },
      );
    }

    const topicKeyword = await prisma.topicKeyword.create({
      data: {
        topicId,
        keyword: keyword.trim(),
      },
    });

    return NextResponse.json(topicKeyword, { status: 201 });
  } catch (error) {
    console.error("Error creating keyword:", error);
    return NextResponse.json(
      { error: "Failed to create keyword" },
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

    await prisma.topicKeyword.delete({ where: { id, topicId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting keyword:", error);
    return NextResponse.json(
      { error: "Failed to delete keyword" },
      { status: 500 },
    );
  }
}
