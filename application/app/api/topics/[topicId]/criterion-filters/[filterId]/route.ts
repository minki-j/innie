import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ topicId: string; filterId: string }>;
}

export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const { topicId, filterId } = await params;

    const topic = await prisma.topic.findFirst({
      where: { id: topicId, userId: session.user.id },
    });
    if (!topic) {
      return NextResponse.json({ error: "Topic not found" }, { status: 404 });
    }

    const filter = await prisma.criterionFilter.findFirst({
      where: { id: filterId, topicId },
    });
    if (!filter) {
      return NextResponse.json({ error: "Filter not found" }, { status: 404 });
    }

    await prisma.criterionFilter.delete({ where: { id: filterId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting criterion filter:", error);
    return NextResponse.json({ error: "Failed to delete criterion filter" }, { status: 500 });
  }
}
