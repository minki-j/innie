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

    // Walk up the ancestor chain to collect all ancestor topics' criteria
    const ancestorCriteria: Array<{
      criterion: { id: string; condition: string; include: boolean; level: string };
      topicId: string;
      topicName: string;
    }> = [];

    let currentParentId = topic.parentId;
    while (currentParentId) {
      const ancestor = await prisma.topic.findFirst({
        where: { id: currentParentId, userId: session.user.id },
        include: {
          criteria: { orderBy: { order: "asc" } },
        },
      });

      if (!ancestor) break;

      for (const criterion of ancestor.criteria) {
        ancestorCriteria.push({
          criterion: {
            id: criterion.id,
            condition: criterion.condition,
            include: criterion.include,
            level: criterion.level,
          },
          topicId: ancestor.id,
          topicName: ancestor.name,
        });
      }

      currentParentId = ancestor.parentId;
    }

    return NextResponse.json(ancestorCriteria);
  } catch (error) {
    console.error("Error fetching ancestor criteria:", error);
    return NextResponse.json({ error: "Failed to fetch ancestor criteria" }, { status: 500 });
  }
}
