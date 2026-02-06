import { prisma } from "@/lib/prisma";
import { YouTubeVideo, VideoTopic } from "@/types/youtube";

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

interface VideoWithTopics {
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
  topics: VideoTopic[];
  summary?: string | null;
}

function videoToYouTubeFormat(v: VideoWithTopics): YouTubeVideo {
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
    topics: v.topics,
    summary: v.summary ?? null,
  };
}

/**
 * Determine if a criterion result is "satisfied" (signals include).
 * - include=true  + PASS → satisfied
 * - include=true  + FAIL → not satisfied
 * - include=false + PASS → not satisfied (exclude condition matched)
 * - include=false + FAIL → satisfied (exclude condition didn't match)
 * - CANNOT_TELL → not satisfied
 */
function isCriterionSatisfied(include: boolean, result: string): boolean {
  if (result === "CANNOT_TELL") return false;
  return include ? result === "PASS" : result === "FAIL";
}

/**
 * Check if a video has any must-have criteria that aren't fully satisfied.
 */
function hasFailingMustHaveCriteria(video: YouTubeVideo): boolean {
  if (!video.topics) return false;
  return video.topics.some(
    (t) =>
      t.totalCriteria != null &&
      t.totalCriteria > 0 &&
      (t.passedCriteria ?? 0) < t.totalCriteria,
  );
}

/** Enrich a raw DB video with criteria scores and convert to YouTubeVideo format. */
function enrichAndFormat(
  v: Parameters<typeof videoToYouTubeFormat>[0] & {
    criterionResults: {
      result: string;
      criterion: { topicId: string; include: boolean; level: string };
    }[];
  },
): YouTubeVideo {
  const topicScores = new Map<string, { passed: number; total: number }>();

  for (const cr of v.criterionResults) {
    const topicId = cr.criterion.topicId;
    if (!topicScores.has(topicId)) {
      topicScores.set(topicId, { passed: 0, total: 0 });
    }
    const score = topicScores.get(topicId)!;
    score.total++;
    if (isCriterionSatisfied(cr.criterion.include, cr.result)) {
      score.passed++;
    }
  }

  const enrichedTopics: VideoTopic[] = v.topics.map((t) => {
    const score = topicScores.get(t.id);
    return {
      id: t.id,
      name: t.name,
      ...(score && {
        passedCriteria: score.passed,
        totalCriteria: score.total,
      }),
    };
  });

  return videoToYouTubeFormat({ ...v, topics: enrichedTopics });
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

// ─── Video include fragment (shared between queries) ─────────

const videoInclude = {
  topics: {
    select: { id: true, name: true },
  },
  criterionResults: {
    where: {
      criterion: { level: "MUST_HAVE" },
    },
    include: {
      criterion: {
        select: { topicId: true, include: true, level: true },
      },
    },
  },
} as const;

// ─── Paginated videos (for API / infinite scroll) ────────────

export interface PaginatedVideosResult {
  videos: YouTubeVideo[];
  nextCursor: string | null;
}

export async function getVideosPaginated(options: {
  topicIds?: string[];
  cursor?: string | null;
  limit: number;
}): Promise<PaginatedVideosResult> {
  const { topicIds, limit } = options;
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

  // Keep fetching batches until we have enough passing videos or run out
  while (collected.length < limit && !exhausted) {
    const batchSize = Math.max(limit * 3, 30);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const where: any = {};

    if (topicIds && topicIds.length > 0) {
      where.topics = { some: { id: { in: topicIds } } };
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
      const enriched = enrichAndFormat(raw);
      if (!hasFailingMustHaveCriteria(enriched)) {
        collected.push({
          video: enriched,
          updatedAt: raw.updatedAt,
          id: raw.id,
        });
      }
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

// ─── All videos (legacy, non-paginated) ──────────────────────

export async function getVideos(topicIds?: string[]): Promise<YouTubeVideo[]> {
  const where =
    topicIds && topicIds.length > 0
      ? { topics: { some: { id: { in: topicIds } } } }
      : {};

  const videos = await prisma.video.findMany({
    where,
    orderBy: { publishedAt: "desc" },
    include: videoInclude,
  });

  return videos.map((v) => enrichAndFormat(v));
}

export async function getVideoById(
  videoId: string,
): Promise<YouTubeVideo | undefined> {
  const v = await prisma.video.findUnique({
    where: { id: videoId },
    include: {
      topics: {
        select: { id: true, name: true },
      },
    },
  });

  if (!v) return undefined;

  const formatted = videoToYouTubeFormat(v);
  formatted.summary = v.summary ?? null;
  return formatted;
}
