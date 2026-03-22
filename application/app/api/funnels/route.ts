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

    const funnels = await prisma.funnel.findMany({
      where: { userId: session.user.id },
      include: {
        _count: {
          select: {
            funnelVideos: true,
            classNodes: true,
            keywords: true,
            creators: true,
          },
        },
      },
      orderBy: { createdAt: "asc" },
    });

    return NextResponse.json(funnels);
  } catch (error) {
    console.error("Error fetching funnels:", error);
    return NextResponse.json(
      { error: "Failed to fetch funnels" },
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
    const { name, description } = body;

    if (!name || typeof name !== "string" || name.trim().length === 0) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }

    const funnel = await prisma.funnel.create({
      data: {
        name: name.trim(),
        description: description?.trim() || null,
        userId: session.user.id,
      },
    });

    return NextResponse.json(funnel, { status: 201 });
  } catch (error) {
    console.error("Error creating funnel:", error);
    return NextResponse.json(
      { error: "Failed to create funnel" },
      { status: 500 },
    );
  }
}
