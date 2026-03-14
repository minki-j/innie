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
  funnels: VideoFunnel[];
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
    funnels: v.funnels,
    summary: v.summary ?? null,
  };
}

// ─── Cursor helpers ──────────────────────────────────────────

function encodeCursor(updatedAt: Date, id: string): string {
  return Buffer.from(
    JSON.stringify({ updatedAt: updatedAt.toISOString(), id }),
  ).toString("base64url");
}

function decodeCursor(cursor: string): { updatedAt: Date; id: string } {
  const parsed = JSON.parse(Buffer.from(cursor, "base64url").toString());
  return { updatedAt: new Date(parsed.updatedAt), id: parsed.id };
}

// ─── Video include fragment ──────────────────────────────────

const videoInclude = {
  funnels: {
    select: { id: true, name: true },
  },
} as const;

// ─── Paginated videos ─────────────────────────────────────────

export interface PaginatedVideosResult {
  videos: YouTubeVideo[];
  nextCursor: string | null;
}

export async function getVideosPaginated(options: {
  funnelIds?: string[];
  cursor?: string | null;
  limit: number;
}): Promise<PaginatedVideosResult> {
  const { funnelIds, limit } = options;
  const cursorData = options.cursor ? decodeCursor(options.cursor) : null;

  interface CollectedItem {
    video: YouTubeVideo;
    updatedAt: Date;
    id: string;
  }

  const collected: CollectedItem[] = [];
  let dbCursorUpdatedAt: Date | null = cursorData?.updatedAt ?? null;
  let dbCursorId: string | null = cursorData?.id ?? null;
  let exhausted = false;

  while (collected.length < limit && !exhausted) {
    const batchSize = Math.max(limit * 3, 30);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const where: any = {};

    if (funnelIds && funnelIds.length > 0) {
      where.funnels = { some: { id: { in: funnelIds } } };
    }

    if (dbCursorUpdatedAt && dbCursorId) {
      where.OR = [
        { updatedAt: { lt: dbCursorUpdatedAt } },
        { updatedAt: dbCursorUpdatedAt, id: { lt: dbCursorId } },
      ];
    }

    const batch = await prisma.video.findMany({
      where,
      orderBy: [{ updatedAt: "desc" }, { id: "desc" }],
      take: batchSize,
      include: videoInclude,
    });

    if (batch.length < batchSize) exhausted = true;

    if (batch.length > 0) {
      const last = batch[batch.length - 1];
      dbCursorUpdatedAt = last.updatedAt;
      dbCursorId = last.id;
    }

    for (const raw of batch) {
      const formatted = videoToYouTubeFormat(raw);
      collected.push({
        video: formatted,
        updatedAt: raw.updatedAt,
        id: raw.id,
      });
    }
  }

  const result = collected.slice(0, limit);

  let nextCursor: string | null = null;
  if (result.length === limit && (collected.length > limit || !exhausted)) {
    const last = result[result.length - 1];
    nextCursor = encodeCursor(last.updatedAt, last.id);
  }

  return { videos: result.map((r) => r.video), nextCursor };
}

export async function getVideos(funnelIds?: string[]): Promise<YouTubeVideo[]> {
  const where =
    funnelIds && funnelIds.length > 0
      ? { funnels: { some: { id: { in: funnelIds } } } }
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
    include: {
      funnels: {
        select: { id: true, name: true },
      },
    },
  });

  if (!v) return undefined;

  const formatted = videoToYouTubeFormat(v);
  formatted.summary = v.summary ?? null;
  return formatted;
}
