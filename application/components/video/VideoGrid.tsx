'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { VideoCard } from './VideoCard';
import { YouTubeVideo } from '@/types/youtube';

// ─── Grid helpers ────────────────────────────────────────────

/** Return number of columns based on the same breakpoints as the CSS grid. */
function getColumns(): number {
  if (typeof window === 'undefined') return 4;
  const w = window.innerWidth;
  if (w >= 1280) return 4; // xl
  if (w >= 1024) return 3; // lg
  if (w >= 640) return 2;  // sm
  return 1;
}

/**
 * Calculate how many videos to fetch so the last visible row is full.
 * Estimates card height (~300px including gap) and accounts for
 * the navbar + topic filter bar (~180px).
 */
function calculatePageSize(): number {
  const cols = getColumns();
  const cardHeight = 300;
  const topOffset = 180;
  const availableHeight =
    typeof window !== 'undefined' ? window.innerHeight - topOffset : 600;
  const rows = Math.max(Math.ceil(availableHeight / cardHeight), 2);
  return rows * cols;
}

// ─── Skeleton ────────────────────────────────────────────────

function VideoCardSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {/* Thumbnail */}
      <div className="relative aspect-video rounded-xl bg-gray-200 animate-pulse" />

      <div className="flex gap-3">
        {/* Avatar */}
        <div className="w-9 h-9 rounded-full bg-gray-200 animate-pulse flex-shrink-0" />

        <div className="flex-1 space-y-2 pt-0.5">
          {/* Title lines */}
          <div className="h-3.5 bg-gray-200 rounded-md animate-pulse w-[92%]" />
          <div className="h-3.5 bg-gray-200 rounded-md animate-pulse w-[60%]" />
          {/* Channel name */}
          <div className="h-3 bg-gray-200 rounded-md animate-pulse w-[40%]" />
          {/* Meta (views + date) */}
          <div className="h-3 bg-gray-200 rounded-md animate-pulse w-[30%]" />
        </div>
      </div>
    </div>
  );
}

function SkeletonGrid({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <VideoCardSkeleton key={`sk-${i}`} />
      ))}
    </>
  );
}

// ─── Main component ──────────────────────────────────────────

interface VideoGridProps {
  selectedFunnelIds: string[];
  selectedClassNodeIds?: string[];
}

export function VideoGrid({ selectedFunnelIds, selectedClassNodeIds = [] }: VideoGridProps) {
  const [videos, setVideos] = useState<YouTubeVideo[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [pageSize, setPageSize] = useState<number | null>(null);

  const sentinelRef = useRef<HTMLDivElement>(null);
  const fetchingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // ── Compute page size on mount ─────────────────────────────

  useEffect(() => {
    setPageSize(calculatePageSize());
  }, []);

  // ── Cleanup in-flight requests on unmount ──────────────────

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // ── Fetch a page of videos from the API ────────────────────

  const fetchPage = useCallback(
    async (pageCursor: string | null, limit: number) => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;
      setLoading(true);

      // Cancel any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const params = new URLSearchParams();
        if (pageCursor) params.set('cursor', pageCursor);
        params.set('limit', String(limit));
        selectedFunnelIds.forEach((id) => params.append('funnel', id));
        selectedClassNodeIds.forEach((id) => params.append('classNode', id));

        const res = await fetch(`/api/videos?${params}`, {
          signal: controller.signal,
        });

        if (!res.ok) throw new Error(`API responded ${res.status}`);
        const data: { videos: YouTubeVideo[]; nextCursor: string | null } =
          await res.json();

        setVideos((prev) =>
          pageCursor ? [...prev, ...data.videos] : data.videos,
        );
        setCursor(data.nextCursor);
        setHasMore(data.nextCursor !== null);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        console.error('Failed to fetch videos:', err);
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedFunnelIds.join(','), selectedClassNodeIds.join(',')],
  );

  // ── Initial fetch (fires once pageSize is known) ───────────

  useEffect(() => {
    if (pageSize !== null) {
      fetchPage(null, pageSize);
    }
  }, [pageSize, fetchPage]);

  // ── Infinite scroll via IntersectionObserver ───────────────

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore || pageSize === null || videos.length === 0)
      return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !fetchingRef.current && cursor) {
          fetchPage(cursor, pageSize);
        }
      },
      { rootMargin: '400px' },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [cursor, hasMore, pageSize, fetchPage, videos.length]);

  // ── Render ─────────────────────────────────────────────────

  const isInitialLoad = videos.length === 0 && loading;
  const skeletonCount = pageSize ?? 12;
  const loadMoreSkeletonCount = getColumns();

  // Empty state — only show after loading finishes
  if (videos.length === 0 && !loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="text-4xl mb-3">🎬</div>
          <p className="text-lg font-medium text-gray-900">No videos found</p>
          <p className="text-sm text-gray-500 mt-1">
            Videos that match your criteria will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-4 gap-y-8">
        {/* Initial full-page skeleton */}
        {isInitialLoad && <SkeletonGrid count={skeletonCount} />}

        {/* Video cards */}
        {videos.map((video) => (
          <VideoCard key={video.id} video={video} />
        ))}

        {/* Loading-more skeletons (single row) */}
        {!isInitialLoad && loading && (
          <SkeletonGrid count={loadMoreSkeletonCount} />
        )}
      </div>

      {/* Scroll sentinel — triggers next page fetch */}
      {hasMore && !isInitialLoad && (
        <div ref={sentinelRef} className="h-px w-full" />
      )}
    </>
  );
}
