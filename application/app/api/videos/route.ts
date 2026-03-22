import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { getUserFunnels } from "@/lib/funnels";
import { getVideosPaginated } from "@/lib/videos";

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = request.nextUrl;
  const cursor = searchParams.get("cursor");
  const limitParam = parseInt(searchParams.get("limit") ?? "24", 10);
  const requestedFunnelIds = searchParams.getAll("funnel").filter(Boolean);
  const classNodeIds = searchParams.getAll("classNode").filter(Boolean);

  const limit = Math.min(Math.max(limitParam, 1), 100);

  const userFunnels = await getUserFunnels();
  const userFunnelIds = userFunnels.map((f) => f.id);

  const scopedFunnelIds =
    requestedFunnelIds.length > 0
      ? requestedFunnelIds.filter((id) => userFunnelIds.includes(id))
      : userFunnelIds;

  const result = await getVideosPaginated({
    funnelIds: scopedFunnelIds,
    classNodeIds: classNodeIds.length > 0 ? classNodeIds : undefined,
    cursor: cursor || null,
    limit,
  });

  return NextResponse.json(result);
}
