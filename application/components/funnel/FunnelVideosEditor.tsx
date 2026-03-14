'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { formatPublishedDate } from '@/lib/youtube/utils';

interface FunnelVideo {
  id: string;
  title: string;
  channelTitle: string;
  thumbnailMedium: string;
  updatedAt: string;
  publishedAt: string;
  classNodeScore: number | null;
  passedNodes: number;
  totalNodes: number;
}

type SortField = 'classNodeScore' | 'updatedAt';
type SortDirection = 'asc' | 'desc';

interface SortOption {
  field: SortField;
  direction: SortDirection;
}

interface FunnelVideosEditorProps {
  funnelId: string;
}

function sortVideos(videos: FunnelVideo[], primary: SortOption, secondary: SortOption): FunnelVideo[] {
  return [...videos].sort((a, b) => {
    const cmp = compareByField(a, b, primary.field, primary.direction);
    if (cmp !== 0) return cmp;
    return compareByField(a, b, secondary.field, secondary.direction);
  });
}

function compareByField(a: FunnelVideo, b: FunnelVideo, field: SortField, direction: SortDirection): number {
  let result = 0;
  if (field === 'classNodeScore') {
    result = (a.classNodeScore ?? -1) - (b.classNodeScore ?? -1);
  } else if (field === 'updatedAt') {
    result = new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
  }
  return direction === 'desc' ? -result : result;
}

const VIDEOS_PER_PAGE = 10;

export function FunnelVideosEditor({ funnelId }: FunnelVideosEditorProps) {
  const [videos, setVideos] = useState<FunnelVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [isReEvaluating, setIsReEvaluating] = useState(false);
  const [reEvalResult, setReEvalResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [isListExpanded, setIsListExpanded] = useState(false);
  const [primarySort, setPrimarySort] = useState<SortOption>({ field: 'classNodeScore', direction: 'desc' });
  const [secondarySort, setSecondarySort] = useState<SortOption>({ field: 'updatedAt', direction: 'desc' });

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/videos`);
      if (!res.ok) throw new Error('Failed to fetch videos');
      const data = await res.json();
      setVideos(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch videos');
    } finally {
      setLoading(false);
    }
  }, [funnelId]);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);
  useEffect(() => { setCurrentPage(0); }, [videos.length]);

  const sortedVideos = useMemo(() => sortVideos(videos, primarySort, secondarySort), [videos, primarySort, secondarySort]);
  const totalPages = Math.max(1, Math.ceil(sortedVideos.length / VIDEOS_PER_PAGE));
  const safePage = Math.min(currentPage, totalPages - 1);
  const paginatedVideos = sortedVideos.slice(safePage * VIDEOS_PER_PAGE, (safePage + 1) * VIDEOS_PER_PAGE);

  const allSelected = videos.length > 0 && selectedIds.size === videos.length;
  const someSelected = selectedIds.size > 0 && !allSelected;

  const toggleSelectAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(videos.map((v) => v.id)));
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    const count = selectedIds.size;
    if (!confirm(`Remove ${count} video${count > 1 ? 's' : ''} from this funnel?`)) return;

    setIsDeleting(true);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/videos`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videoIds: Array.from(selectedIds) }),
      });
      if (!res.ok) throw new Error('Failed to remove videos');
      setVideos((prev) => prev.filter((v) => !selectedIds.has(v.id)));
      setSelectedIds(new Set());
    } catch (err) {
      console.error(err);
      alert('Failed to remove videos. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleReEvaluate = async () => {
    if (selectedIds.size === 0) return;
    const count = selectedIds.size;
    if (!confirm(`Re-evaluate ${count} video${count > 1 ? 's' : ''}?`)) return;

    setIsReEvaluating(true);
    setReEvalResult(null);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/re-evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ videoIds: Array.from(selectedIds) }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to start re-evaluation');
      }
      setReEvalResult({ type: 'success', message: `Re-evaluation started for ${count} video${count > 1 ? 's' : ''}.` });
      setSelectedIds(new Set());
    } catch (err) {
      setReEvalResult({ type: 'error', message: err instanceof Error ? err.message : 'Failed to start re-evaluation.' });
    } finally {
      setIsReEvaluating(false);
      setTimeout(() => setReEvalResult(null), 8000);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading videos...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-red-600">{error}</p>
        <button onClick={fetchVideos} className="mt-2 text-sm text-blue-600 hover:text-blue-700">Retry</button>
      </div>
    );
  }

  if (videos.length === 0) {
    return <div className="text-center py-8 text-gray-500"><p className="text-sm">No videos have been processed for this funnel yet.</p></div>;
  }

  return (
    <div className="space-y-3">
      <button
        onClick={() => setIsListExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${isListExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-sm font-medium text-gray-700">Videos</span>
          <span className="text-xs text-gray-400">({videos.length} video{videos.length !== 1 ? 's' : ''})</span>
        </div>
        {selectedIds.size > 0 && <span className="text-xs text-blue-600 font-medium">{selectedIds.size} selected</span>}
      </button>

      {isListExpanded && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Sort by</span>
              <select
                value={primarySort.field}
                onChange={(e) => setPrimarySort({ ...primarySort, field: e.target.value as SortField })}
                className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white text-gray-700 focus:outline-none"
              >
                <option value="classNodeScore">Class Node Score</option>
                <option value="updatedAt">Updated At</option>
              </select>
            </div>
            <div className="flex items-center gap-3">
              {selectedIds.size > 0 && (
                <>
                  <button onClick={handleReEvaluate} disabled={isReEvaluating} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100 transition-colors disabled:opacity-50">
                    {isReEvaluating ? 'Starting...' : 'Re-evaluate'}
                  </button>
                  <button onClick={handleBulkDelete} disabled={isDeleting} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 rounded-md hover:bg-red-100 transition-colors disabled:opacity-50">
                    {isDeleting ? 'Removing...' : 'Remove Selected'}
                  </button>
                </>
              )}
            </div>
          </div>

          {reEvalResult && (
            <div className={`text-sm px-3 py-2 rounded-lg ${reEvalResult.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
              {reEvalResult.message}
            </div>
          )}

          <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-t-lg border border-gray-200 border-b-0">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(el) => { if (el) el.indeterminate = someSelected; }}
                onChange={toggleSelectAll}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-xs font-medium text-gray-600">
                {allSelected ? 'Deselect All' : 'Select All'}
                {selectedIds.size > 0 && <span className="text-gray-400 ml-1">({selectedIds.size} of {videos.length})</span>}
              </span>
            </label>
          </div>

          <div className="-mt-3 border border-gray-200 rounded-b-lg divide-y divide-gray-100 overflow-hidden">
            {paginatedVideos.map((video) => (
              <div key={video.id} className={`flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors ${selectedIds.has(video.id) ? 'bg-blue-50/50' : ''}`}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(video.id)}
                  onChange={() => toggleSelect(video.id)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 flex-shrink-0"
                />
                <Link href={`/watch/${video.id}`} className="flex-shrink-0 relative w-28 aspect-video rounded-md overflow-hidden bg-gray-100">
                  <Image src={video.thumbnailMedium} alt={video.title} fill className="object-cover" sizes="112px" />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link href={`/watch/${video.id}`} className="text-sm font-medium text-gray-900 hover:text-blue-600 line-clamp-1 transition-colors">{video.title}</Link>
                  <p className="text-xs text-gray-500 mt-0.5">{video.channelTitle}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                    <span>Published {formatPublishedDate(video.publishedAt)}</span>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right">
                  {video.totalNodes > 0 ? (
                    <div className="flex flex-col items-end gap-0.5">
                      <span className={`text-sm font-semibold ${video.classNodeScore !== null && video.classNodeScore >= 1 ? 'text-green-600' : video.classNodeScore !== null && video.classNodeScore >= 0.5 ? 'text-yellow-600' : 'text-red-600'}`}>
                        {video.passedNodes}/{video.totalNodes}
                      </span>
                      <span className="text-[10px] text-gray-400">nodes</span>
                    </div>
                  ) : (
                    <span className="text-xs text-gray-400">No results</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-gray-400">Showing {safePage * VIDEOS_PER_PAGE + 1}–{Math.min((safePage + 1) * VIDEOS_PER_PAGE, sortedVideos.length)} of {sortedVideos.length}</span>
              <div className="flex items-center gap-1">
                <button onClick={() => setCurrentPage(0)} disabled={safePage === 0} className="px-2 py-1 text-xs text-gray-600 rounded hover:bg-gray-100 disabled:opacity-30">«</button>
                <button onClick={() => setCurrentPage((p) => Math.max(0, p - 1))} disabled={safePage === 0} className="px-2 py-1 text-xs text-gray-600 rounded hover:bg-gray-100 disabled:opacity-30">‹</button>
                <span className="text-xs text-gray-500 px-2">{safePage + 1} / {totalPages}</span>
                <button onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))} disabled={safePage >= totalPages - 1} className="px-2 py-1 text-xs text-gray-600 rounded hover:bg-gray-100 disabled:opacity-30">›</button>
                <button onClick={() => setCurrentPage(totalPages - 1)} disabled={safePage >= totalPages - 1} className="px-2 py-1 text-xs text-gray-600 rounded hover:bg-gray-100 disabled:opacity-30">»</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
