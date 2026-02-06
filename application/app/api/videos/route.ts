import { NextRequest, NextResponse } from "next/server";
import { getVideosPaginated } from "@/lib/videos";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const cursor = searchParams.get("cursor");
  const limitParam = parseInt(searchParams.get("limit") ?? "24", 10);
  const topicIds = searchParams.getAll("topic").filter(Boolean);

  const limit = Math.min(Math.max(limitParam, 1), 100);

  const result = await getVideosPaginated({
    topicIds: topicIds.length > 0 ? topicIds : undefined,
    cursor: cursor || null,
    limit,
  });

  return NextResponse.json(result);
}
