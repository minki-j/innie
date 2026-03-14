import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { ClassNodeResultValue } from "@/lib/generated/prisma/client";

interface RouteParams {
  params: Promise<{ videoId: string }>;
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

    const classNodeResults = await prisma.classNodeResult.findMany({
      where: { videoId },
      include: {
        classNode: {
          include: {
            funnel: {
              select: { id: true, name: true, userId: true },
            },
          },
        },
      },
    });

    // Only show results for funnels owned by this user
    const userResults = classNodeResults.filter(
      (r) => r.classNode.funnel?.userId === session.user!.id,
    );

    // Group results by funnel
    const grouped: Record<
      string,
      {
        funnelId: string;
        funnelName: string;
        results: {
          id: string;
          classNodeId: string;
          description: string;
          result: string;
          explanation: string | null;
          confidence: number | null;
        }[];
      }
    > = {};

    for (const r of userResults) {
      const funnelId = r.classNode.funnel!.id;
      const funnelName = r.classNode.funnel!.name;

      if (!grouped[funnelId]) {
        grouped[funnelId] = {
          funnelId,
          funnelName,
          results: [],
        };
      }

      grouped[funnelId].results.push({
        id: r.id,
        classNodeId: r.classNodeId,
        description: r.classNode.description,
        result: r.result,
        explanation: r.explanation,
        confidence: r.confidence,
      });
    }

    return NextResponse.json(Object.values(grouped));
  } catch (error) {
    console.error("Error fetching class node results:", error);
    return NextResponse.json(
      { error: "Failed to fetch class node results" },
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

    const { videoId } = await params;
    const body = await request.json();
    const { updates } = body as {
      updates: {
        id: string;
        result: ClassNodeResultValue;
        explanation: string | null;
      }[];
    };

    if (!Array.isArray(updates) || updates.length === 0) {
      return NextResponse.json(
        { error: "updates array is required" },
        { status: 400 },
      );
    }

    const existingResults = await prisma.classNodeResult.findMany({
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
            "Some class node result IDs are invalid or do not belong to this video",
        },
        { status: 400 },
      );
    }

    await Promise.all(
      updates.map((u) =>
        prisma.classNodeResult.update({
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
    console.error("Error updating class node results:", error);
    return NextResponse.json(
      { error: "Failed to update class node results" },
      { status: 500 },
    );
  }
}
