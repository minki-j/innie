import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

interface RouteParams {
  params: Promise<{ classNodeId: string }>;
}

async function verifyClassNodeOwnership(classNodeId: string, userId: string) {
  return prisma.classNode.findFirst({
    where: {
      id: classNodeId,
      funnel: { userId },
    },
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

    const { classNodeId } = await params;
    const classNode = await verifyClassNodeOwnership(classNodeId, session.user.id);
    if (!classNode) {
      return NextResponse.json(
        { error: "Class node not found" },
        { status: 404 },
      );
    }

    return NextResponse.json(classNode);
  } catch (error) {
    console.error("Error fetching class node:", error);
    return NextResponse.json(
      { error: "Failed to fetch class node" },
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

    const { classNodeId } = await params;
    if (!(await verifyClassNodeOwnership(classNodeId, session.user.id))) {
      return NextResponse.json(
        { error: "Class node not found" },
        { status: 404 },
      );
    }

    const body = await request.json();
    const { description } = body;

    if (
      description !== undefined &&
      (typeof description !== "string" || description.trim().length === 0)
    ) {
      return NextResponse.json(
        { error: "description cannot be empty" },
        { status: 400 },
      );
    }

    const classNode = await prisma.classNode.update({
      where: { id: classNodeId },
      data: {
        ...(description !== undefined && { description: description.trim() }),
      },
    });

    return NextResponse.json(classNode);
  } catch (error) {
    console.error("Error updating class node:", error);
    return NextResponse.json(
      { error: "Failed to update class node" },
      { status: 500 },
    );
  }
}

async function collectDescendantIds(parentId: string): Promise<string[]> {
  const children = await prisma.classNode.findMany({
    where: { parentClassNodeId: parentId },
    select: { id: true },
  });
  const ids: string[] = [];
  for (const child of children) {
    ids.push(child.id);
    ids.push(...(await collectDescendantIds(child.id)));
  }
  return ids;
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

    const { classNodeId } = await params;
    if (!(await verifyClassNodeOwnership(classNodeId, session.user.id))) {
      return NextResponse.json(
        { error: "Class node not found" },
        { status: 404 },
      );
    }

    const descendantIds = await collectDescendantIds(classNodeId);
    const allIds = [classNodeId, ...descendantIds];

    await prisma.classNode.deleteMany({ where: { id: { in: allIds } } });

    return NextResponse.json({ success: true, deletedIds: allIds });
  } catch (error) {
    console.error("Error deleting class node:", error);
    return NextResponse.json(
      { error: "Failed to delete class node" },
      { status: 500 },
    );
  }
}
