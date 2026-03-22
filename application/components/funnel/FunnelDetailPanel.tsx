'use client';

import { useEffect, useState } from 'react';
import { FunnelOverviewEditor } from '@/components/funnel/FunnelOverviewEditor';
import { FunnelPanels } from '@/components/funnel/FunnelPanels';

interface FunnelKeyword {
  id: string;
  keyword: string;
}

interface FunnelCreator {
  id: string;
  channelId: string | null;
  channelUrl: string | null;
  channelName: string | null;
  scrapeMonthsBack: number;
}

interface FunnelDetail {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  pipelineIntervalHours: number;
  lastPipelineRunAt: string | null;
  maxVideosPerKeyword: number;
  maxVideosPerCreator: number;
  keywords: FunnelKeyword[];
  creators: FunnelCreator[];
  _count: { funnelVideos: number; classNodes: number };
}

interface Props {
  funnelId: string;
  onClose: () => void;
}

export function FunnelDetailPanel({ funnelId, onClose }: Props) {
  const [funnel, setFunnel] = useState<FunnelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    setLoading(true);
    setFunnel(null);
    fetch(`/api/funnels/${funnelId}`)
      .then((r) => r.json())
      .then((data) => {
        setFunnel(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [funnelId]);

  const handleDelete = async () => {
    if (!funnel) return;
    if (!confirm(`Delete "${funnel.name}"? This cannot be undone.`)) return;

    setDeleting(true);
    const res = await fetch(`/api/funnels/${funnelId}`, { method: 'DELETE' });
    if (res.ok) {
      window.dispatchEvent(new CustomEvent('funnel-deleted', { detail: { funnelId } }));
      onClose();
    }
    setDeleting(false);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <span className="text-sm text-gray-400">Topic detail</span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
            title="Delete topic"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="Close panel"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overscroll-none px-5 py-5 space-y-8">
        {loading && <div className="py-16 text-center text-sm text-gray-400">Loading…</div>}
        {!loading && !funnel && <div className="py-16 text-center text-sm text-red-400">Topic not found.</div>}

        {!loading && funnel && (
          <>
            <FunnelOverviewEditor
              funnelId={funnel.id}
              initialName={funnel.name}
              initialDescription={funnel.description}
            />

            <FunnelPanels
              funnelId={funnel.id}
              active={funnel.active}
              pipelineIntervalHours={funnel.pipelineIntervalHours}
              lastPipelineRunAt={funnel.lastPipelineRunAt}
              maxVideosPerKeyword={funnel.maxVideosPerKeyword}
              maxVideosPerCreator={funnel.maxVideosPerCreator}
              keywords={funnel.keywords}
              creators={funnel.creators}
            />
          </>
        )}
      </div>
    </div>
  );
}
