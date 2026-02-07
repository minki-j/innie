import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { CriterionResultValue } from "@/lib/generated/prisma/client";

interface RouteParams {
  params: Promise<{ videoId: string }>;
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

    const { videoId } = await params;
    const body = await request.json();
    const { updates } = body as {
      updates: {
        id: string;
        result: CriterionResultValue;
        explanation: string | null;
      }[];
    };

    if (!Array.isArray(updates) || updates.length === 0) {
      return NextResponse.json(
        { error: "updates array is required" },
        { status: 400 },
      );
    }

    // Validate all results belong to this video
    const existingResults = await prisma.criterionResult.findMany({
      where: {
        id: { in: updates.map((u) => u.id) },
        videoId,
      },
      select: { id: true },
    });

    const existingIds = new Set(existingResults.map((r) => r.id));
    const invalidIds = updates.filter((u) => !existingIds.has(u.id));

    if (invalidIds.length > 0) {
      return NextResponse.json(
        {
          error:
            "Some criterion result IDs are invalid or do not belong to this video",
        },
        { status: 400 },
      );
    }

    // Batch update
    await Promise.all(
      updates.map((u) =>
        prisma.criterionResult.update({
          where: { id: u.id },
          data: {
            result: u.result,
            explanation: u.explanation,
          },
        }),
      ),
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error updating criterion results:", error);
    return NextResponse.json(
      { error: "Failed to update criterion results" },
      { status: 500 },
    );
  }
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    const { videoId } = await params;

    const criterionResults = await prisma.criterionResult.findMany({
      where: { videoId },
      include: {
        criterion: {
          include: {
            topic: {
              select: { id: true, name: true },
            },
          },
        },
      },
      orderBy: { criterion: { order: "asc" } },
    });

    // Group results by topic
    const grouped: Record<
      string,
      {
        topicId: string;
        topicName: string;
        results: {
          id: string;
          condition: string;
          include: boolean;
          level: string;
          result: string;
          explanation: string | null;
        }[];
      }
    > = {};

    for (const cr of criterionResults) {
      const topicId = cr.criterion.topic.id;
      const topicName = cr.criterion.topic.name;

      if (!grouped[topicId]) {
        grouped[topicId] = {
          topicId,
          topicName,
          results: [],
        };
      }

      grouped[topicId].results.push({
        id: cr.id,
        condition: cr.criterion.condition,
        include: cr.criterion.include,
        level: cr.criterion.level,
        result: cr.result,
        explanation: cr.explanation,
      });
    }

    return NextResponse.json(Object.values(grouped));
  } catch (error) {
    console.error("Error fetching criterion results:", error);
    return NextResponse.json(
      { error: "Failed to fetch criterion results" },
      { status: 500 },
    );
  }
}
