'use client';

import { useEffect, useState } from 'react';
import { TopicOverviewEditor } from '@/components/topic/TopicOverviewEditor';
import { TopicPanels } from '@/components/topic/TopicPanels';

interface CriterionFilter {
  id: string;
  criterionId: string;
  requiredResult: string;
  criterion: { id: string; condition: string; include: boolean; topicId: string };
}

interface Criterion {
  id: string;
  condition: string;
  include: boolean;
  level: string;
  order: number;
}

interface GoldStandard {
  id: string;
  videoUrl: string;
  title: string | null;
  isPositive: boolean;
  note: string | null;
}

interface TopicKeyword {
  id: string;
  keyword: string;
}

interface TopicCreator {
  id: string;
  channelId: string | null;
  channelUrl: string | null;
  channelName: string | null;
  scrapeMonthsBack: number;
}

interface TopicDetail {
  id: string;
  name: string;
  description: string | null;
  parentId: string | null;
  active: boolean;
  pipelineIntervalHours: number;
  lastPipelineRunAt: string | null;
  criteria: Criterion[];
  criterionFilters: CriterionFilter[];
  goldStandards: GoldStandard[];
  keywords: TopicKeyword[];
  creators: TopicCreator[];
  children: { id: string; name: string }[];
  _count: { videos: number; criteria: number; criterionFilters: number };
}

interface Props {
  topicId: string;
  onClose: () => void;
}

export function TopicDetailPanel({ topicId, onClose }: Props) {
  const [topic, setTopic] = useState<TopicDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    setLoading(true);
    setTopic(null);
    fetch(`/api/topics/${topicId}`)
      .then((r) => r.json())
      .then((data) => {
        setTopic(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [topicId]);

  const handleDelete = async () => {
    if (!topic) return;
    const hasChildren = topic.children.length > 0;
    const msg = hasChildren
      ? `Delete "${topic.name}" and all its child topics? This cannot be undone.`
      : `Delete "${topic.name}"? This cannot be undone.`;
    if (!confirm(msg)) return;

    setDeleting(true);
    const res = await fetch(`/api/topics/${topicId}`, { method: 'DELETE' });
    if (res.ok) {
      window.dispatchEvent(new CustomEvent('topic-deleted', { detail: { topicId } }));
      onClose();
    }
    setDeleting(false);
  };

  const isRoot = !topic?.parentId;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-2">
          {isRoot && (
            <span className="px-2 py-0.5 text-xs font-semibold bg-violet-100 text-violet-700 rounded">
              ROOT
            </span>
          )}
          {!isRoot && (
            <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 rounded">
              CHILD
            </span>
          )}
          <span className="text-sm text-gray-400">Topic detail</span>
        </div>
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

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-8">
        {loading && (
          <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
        )}

        {!loading && !topic && (
          <div className="py-16 text-center text-sm text-red-400">Topic not found.</div>
        )}

        {!loading && topic && (
          <>
            {/* Overview editor */}
            <TopicOverviewEditor
              topicId={topic.id}
              initialName={topic.name}
              initialDescription={topic.description}
            />

            {/* Breadcrumb / parent info */}
            {!isRoot && (
              <div className="text-xs text-gray-400">
                Child of a parent topic — receives videos filtered from parent.
              </div>
            )}

            {/* Tabs */}
            <TopicPanels
              topicId={topic.id}
              isRoot={isRoot}
              active={topic.active}
              pipelineIntervalHours={topic.pipelineIntervalHours}
              lastPipelineRunAt={topic.lastPipelineRunAt}
              criteria={topic.criteria}
              goldStandards={topic.goldStandards}
              keywords={topic.keywords}
              creators={topic.creators}
            />
          </>
        )}
      </div>
    </div>
  );
}
