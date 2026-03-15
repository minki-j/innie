import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ funnelId: string }>;
}

async function verifyFunnelOwnership(funnelId: string, userId: string) {
  return prisma.funnel.findFirst({
    where: { id: funnelId, userId },
  });
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
    if (!(await verifyFunnelOwnership(funnelId, session.user.id))) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const classNodes = await prisma.classNode.findMany({
      where: { funnelId },
      include: {
        goldStandards: { orderBy: { createdAt: "desc" } },
        _count: { select: { results: true, childrenClassNodes: true } },
      },
      orderBy: { createdAt: "asc" },
    });

    return NextResponse.json(classNodes);
  } catch (error) {
    console.error("Error fetching class nodes:", error);
    return NextResponse.json(
      { error: "Failed to fetch class nodes" },
      { status: 500 },
    );
  }
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

    const { funnelId } = await params;
    if (!(await verifyFunnelOwnership(funnelId, session.user.id))) {
      return NextResponse.json({ error: "Funnel not found" }, { status: 404 });
    }

    const body = await request.json();
    const { title, description, parentClassNodeId } = body;

    if (!title || typeof title !== "string" || title.trim().length === 0) {
      return NextResponse.json(
        { error: "title is required" },
        { status: 400 },
      );
    }

    if (
      description !== undefined &&
      description !== null &&
      (typeof description !== "string" || description.trim().length === 0)
    ) {
      return NextResponse.json(
        { error: "description cannot be empty string" },
        { status: 400 },
      );
    }

    if (parentClassNodeId) {
      const parent = await prisma.classNode.findFirst({
        where: { id: parentClassNodeId, funnelId },
      });
      if (!parent) {
        return NextResponse.json(
          { error: "Parent class node not found" },
          { status: 404 },
        );
      }
    }

    const classNode = await prisma.classNode.create({
      data: {
        title: title.trim(),
        description: description ? description.trim() : null,
        funnelId,
        parentClassNodeId: parentClassNodeId || null,
      },
    });

    return NextResponse.json(classNode, { status: 201 });
  } catch (error) {
    console.error("Error creating class node:", error);
    return NextResponse.json(
      { error: "Failed to create class node" },
      { status: 500 },
    );
  }
}
