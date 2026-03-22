import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ funnelId: string }>;
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

    const { funnelId } = await params;

    const funnel = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
      include: {
        classNodes: {
          orderBy: { createdAt: "asc" },
        },
        keywords: { orderBy: { createdAt: "desc" } },
        creators: { orderBy: { createdAt: "desc" } },
        _count: { select: { funnelVideos: true, classNodes: true } },
      },
    });

    if (!funnel) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    return NextResponse.json(funnel);
  } catch (error) {
    console.error("Error fetching funnel:", error);
    return NextResponse.json(
      { error: "Failed to fetch funnel" },
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

    const { funnelId } = await params;

    const existing = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const body = await request.json();
    const { name, description, active, pipelineIntervalHours, maxVideosPerKeyword, maxVideosPerCreator } = body;

    const funnel = await prisma.funnel.update({
      where: { id: funnelId },
      data: {
        ...(name !== undefined && { name: name.trim() }),
        ...(description !== undefined && {
          description: description?.trim() || null,
        }),
        ...(active !== undefined && { active: Boolean(active) }),
        ...(pipelineIntervalHours !== undefined && {
          pipelineIntervalHours: Math.max(1, Math.min(168, Number(pipelineIntervalHours))),
        }),
        ...(maxVideosPerKeyword !== undefined && {
          maxVideosPerKeyword: Math.max(1, Math.min(200, Number(maxVideosPerKeyword))),
        }),
        ...(maxVideosPerCreator !== undefined && {
          maxVideosPerCreator: Math.max(1, Math.min(200, Number(maxVideosPerCreator))),
        }),
      },
    });

    return NextResponse.json(funnel);
  } catch (error) {
    console.error("Error updating funnel:", error);
    return NextResponse.json(
      { error: "Failed to update funnel" },
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

    const { funnelId } = await params;

    const existing = await prisma.funnel.findFirst({
      where: { id: funnelId, userId: session.user.id },
    });

    if (!existing) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    await prisma.funnel.delete({ where: { id: funnelId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting funnel:", error);
    return NextResponse.json(
      { error: "Failed to delete funnel" },
      { status: 500 },
    );
  }
}
