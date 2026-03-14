import { NextRequest, NextResponse } from "next/server";
import { getVideosPaginated } from "@/lib/videos";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const cursor = searchParams.get("cursor");
  const limitParam = parseInt(searchParams.get("limit") ?? "24", 10);
  const funnelIds = searchParams.getAll("funnel").filter(Boolean);

  const limit = Math.min(Math.max(limitParam, 1), 100);

  const result = await getVideosPaginated({
    funnelIds: funnelIds.length > 0 ? funnelIds : undefined,
    cursor: cursor || null,
    limit,
  });

  return NextResponse.json(result);
}
