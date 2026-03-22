import { Prisma } from "@/lib/generated/prisma/client";
import { prisma } from "@/lib/prisma";
import { YouTubeVideo, VideoFunnel } from "@/types/youtube";

function secondsToIsoDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  let duration = "PT";
  if (hours > 0) duration += `${hours}H`;
  if (minutes > 0) duration += `${minutes}M`;
  if (seconds > 0 || duration === "PT") duration += `${seconds}S`;
  return duration;
}

interface VideoWithFunnels {
  id: string;
  title: string;
  description: string;
  channelTitle: string;
  channelId: string;
  publishedAt: Date;
  viewCount: bigint;
  likeCount: bigint;
  commentCount: bigint;
  durationSeconds: number;
  definition: string;
  caption: string;
  tags: string[];
  thumbnailDefault: string | null;
  thumbnailMedium: string | null;
  thumbnailHigh: string | null;
  funnelVideos: Array<{ funnel: VideoFunnel }>;
  summary?: string | null;
}

function videoToYouTubeFormat(v: VideoWithFunnels): YouTubeVideo {
  return {
    kind: "youtube#video",
    etag: "",
    id: v.id,
    snippet: {
      title: v.title,
      description: v.description,
      channelTitle: v.channelTitle,
      channelId: v.channelId,
      publishedAt: v.publishedAt.toISOString(),
      tags: v.tags,
      thumbnails: {
        default: {
          url:
            v.thumbnailDefault ?? `https://i.ytimg.com/vi/${v.id}/default.jpg`,
          width: 120,
          height: 90,
        },
        medium: {
          url:
            v.thumbnailMedium ?? `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`,
          width: 320,
          height: 180,
        },
        high: {
          url:
            v.thumbnailHigh ?? `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`,
          width: 480,
          height: 360,
        },
      },
    },
    statistics: {
      viewCount: String(v.viewCount),
      likeCount: String(v.likeCount),
      commentCount: String(v.commentCount),
    },
    contentDetails: {
      duration: secondsToIsoDuration(v.durationSeconds),
      definition: v.definition,
      caption: v.caption,
    },
    funnels: v.funnelVideos.map((fv) => fv.funnel),
    summary: v.summary ?? null,
  };
}

// ─── Cursor helpers ──────────────────────────────────────────

function encodeCursor(lastProcessedAt: Date, id: string): string {
  return Buffer.from(
    JSON.stringify({ lastProcessedAt: lastProcessedAt.toISOString(), id }),
  ).toString("base64url");
}

function decodeCursor(cursor: string): { lastProcessedAt: Date; id: string } {
  const parsed = JSON.parse(Buffer.from(cursor, "base64url").toString());
  return { lastProcessedAt: new Date(parsed.lastProcessedAt), id: parsed.id };
}

// ─── Video include fragment ──────────────────────────────────

const videoInclude = {
  funnelVideos: {
    select: {
      funnel: { select: { id: true, name: true } },
    },
  },
} as const;

// ─── Paginated videos ─────────────────────────────────────────

export interface PaginatedVideosResult {
  videos: YouTubeVideo[];
  nextCursor: string | null;
}

export async function getVideosPaginated(options: {
  funnelIds: string[];
  classNodeIds?: string[];
  cursor?: string | null;
  limit: number;
}): Promise<PaginatedVideosResult> {
  const { funnelIds, classNodeIds, limit } = options;

  if (funnelIds.length === 0) {
    return { videos: [], nextCursor: null };
  }

  const cursorData = options.cursor ? decodeCursor(options.cursor) : null;

  // One EXISTS sub-select per classNodeId (AND semantics)
  const classNodeFragments = (classNodeIds ?? []).map(
    (id) => Prisma.sql`
      AND EXISTS (
        SELECT 1 FROM "ClassNodeResult" cnr
        WHERE cnr."videoId" = v.id
          AND cnr."classNodeId" = ${id}
          AND cnr."result" = 'PASS'
      )`,
  );
  const classNodeSql =
    classNodeFragments.length > 0
      ? Prisma.join(classNodeFragments, "")
      : Prisma.empty;

  // Cursor: filter rows that come after the last seen position
  const cursorSql = cursorData
    ? Prisma.sql`HAVING (
        MAX(fv."updatedAt") < ${cursorData.lastProcessedAt}
        OR (MAX(fv."updatedAt") = ${cursorData.lastProcessedAt} AND v.id < ${cursorData.id})
      )`
    : Prisma.empty;

  type RawRow = { id: string; last_processed_at: Date };

  const rows = await prisma.$queryRaw<RawRow[]>(Prisma.sql`
    SELECT v.id, MAX(fv."updatedAt") AS last_processed_at
    FROM "Video" v
    JOIN "FunnelVideo" fv ON fv."videoId" = v.id
    WHERE fv."funnelId" = ANY(${funnelIds}::text[])
      AND fv."status" = 'COMPLETED'
      ${classNodeSql}
    GROUP BY v.id
    ${cursorSql}
    ORDER BY last_processed_at DESC, v.id DESC
    LIMIT ${limit + 1}
  `);

  const hasMore = rows.length > limit;
  const pageRows = hasMore ? rows.slice(0, limit) : rows;
  const videoIds = pageRows.map((r) => r.id);

  if (videoIds.length === 0) {
    return { videos: [], nextCursor: null };
  }

  const videos = await prisma.video.findMany({
    where: { id: { in: videoIds } },
    include: videoInclude,
  });

  const videoMap = new Map(videos.map((v) => [v.id, v]));
  const orderedVideos = videoIds
    .map((id) => videoMap.get(id))
    .filter((v): v is NonNullable<typeof v> => v !== undefined)
    .map((v) => videoToYouTubeFormat(v));

  let nextCursor: string | null = null;
  if (hasMore) {
    const last = pageRows[pageRows.length - 1];
    nextCursor = encodeCursor(last.last_processed_at, last.id);
  }

  return { videos: orderedVideos, nextCursor };
}

export async function getVideos(funnelIds?: string[]): Promise<YouTubeVideo[]> {
  const where =
    funnelIds && funnelIds.length > 0
      ? { funnelVideos: { some: { funnelId: { in: funnelIds } } } }
      : {};

  const videos = await prisma.video.findMany({
    where,
    orderBy: { publishedAt: "desc" },
    include: videoInclude,
  });

  return videos.map((v) => videoToYouTubeFormat(v));
}

export async function getVideoById(
  videoId: string,
): Promise<YouTubeVideo | undefined> {
  const v = await prisma.video.findUnique({
    where: { id: videoId },
    include: videoInclude,
  });

  if (!v) return undefined;

  const formatted = videoToYouTubeFormat(v);
  formatted.summary = v.summary ?? null;
  return formatted;
}
