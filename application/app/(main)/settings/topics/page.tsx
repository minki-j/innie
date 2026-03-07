'use client';

import { useEffect, useState } from 'react';
import { TopicFlowCanvas, type TopicSummary } from '@/components/topic/TopicFlowCanvas';
import { TopicDetailPanel } from '@/components/topic/TopicDetailPanel';

export default function TopicsPage() {
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/topics')
      .then((r) => r.json())
      .then((data: TopicSummary[]) => {
        setTopics(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const panelOpen = selectedId !== null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-400">
        Loading topics…
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Canvas area */}
      <div
        className="flex-1 relative"
        style={{ height: 'calc(100vh - 64px)' }}
      >
        {topics.length === 0 && !loading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-gray-400">
            <svg className="w-16 h-16 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p className="text-lg font-medium text-gray-500">No topics yet</p>
            <p className="text-sm">Click &quot;New Root Topic&quot; in the canvas to get started.</p>
          </div>
        ) : null}
        <TopicFlowCanvas
          initialTopics={topics}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>

      {/* Right detail panel */}
      {panelOpen && selectedId && (
        <div
          className="w-[480px] shrink-0 border-l border-gray-200 overflow-hidden"
          style={{ height: 'calc(100vh - 64px)' }}
        >
          <TopicDetailPanel
            key={selectedId}
            topicId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </div>
  );
}
