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

export async function POST(request: NextRequest, { params }: RouteParams) {
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
    const { videoUrl, title, isPositive = true, note } = body;

    if (
      !videoUrl ||
      typeof videoUrl !== "string" ||
      videoUrl.trim().length === 0
    ) {
      return NextResponse.json(
        { error: "videoUrl is required" },
        { status: 400 },
      );
    }

    const goldStandard = await prisma.goldStandard.create({
      data: {
        classNodeId,
        videoUrl: videoUrl.trim(),
        title: title?.trim() || null,
        isPositive: Boolean(isPositive),
        note: note?.trim() || null,
      },
    });

    return NextResponse.json(goldStandard, { status: 201 });
  } catch (error) {
    console.error("Error creating gold standard:", error);
    return NextResponse.json(
      { error: "Failed to create gold standard" },
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

    const { classNodeId } = await params;
    if (!(await verifyClassNodeOwnership(classNodeId, session.user.id))) {
      return NextResponse.json(
        { error: "Class node not found" },
        { status: 404 },
      );
    }

    const { searchParams } = request.nextUrl;
    const id = searchParams.get("id");

    if (!id) {
      return NextResponse.json({ error: "id is required" }, { status: 400 });
    }

    await prisma.goldStandard.delete({ where: { id, classNodeId } });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting gold standard:", error);
    return NextResponse.json(
      { error: "Failed to delete gold standard" },
      { status: 500 },
    );
  }
}
