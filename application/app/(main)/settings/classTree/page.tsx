'use client';

import { useEffect, useState } from 'react';
import { FunnelFlowCanvas, type FunnelSummary, type SelectedClassNode } from '@/components/funnel/FunnelFlowCanvas';
import { FunnelDetailPanel } from '@/components/funnel/FunnelDetailPanel';
import { ClassNodeDetailPanel } from '@/components/funnel/ClassNodeDetailPanel';

export default function ClassificationTreePage() {
  const [funnels, setFunnels] = useState<FunnelSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFunnelId, setSelectedFunnelId] = useState<string | null>(null);
  const [selectedClassNode, setSelectedClassNode] = useState<SelectedClassNode | null>(null);

  useEffect(() => {
    document.title = 'Classification Tree – Innie';
  }, []);

  useEffect(() => {
    fetch('/api/funnels')
      .then((r) => r.json())
      .then((data: FunnelSummary[]) => {
        setFunnels(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const panelOpen = selectedFunnelId !== null || selectedClassNode !== null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-400">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      <div
        className="flex-1 relative"
        style={{ height: 'calc(100vh - 64px)' }}
      >
        {funnels.length === 0 && !loading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-gray-400">
            <svg className="w-16 h-16 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p className="text-lg font-medium text-gray-500">No topics yet</p>
            <p className="text-sm">Click &quot;New Topic&quot; in the canvas to get started.</p>
          </div>
        ) : null}
        <FunnelFlowCanvas
          initialFunnels={funnels}
          selectedFunnelId={selectedFunnelId}
          selectedClassNodeId={selectedClassNode?.id ?? null}
          onSelectFunnel={(id) => {
            setSelectedFunnelId(id);
            setSelectedClassNode(null);
          }}
          onSelectClassNode={(cn) => {
            setSelectedClassNode(cn);
            setSelectedFunnelId(null);
          }}
          onFunnelAdded={(funnel) => setFunnels((prev) => [...prev, funnel])}
        />
      </div>

      {panelOpen && (
        <div
          className="w-[480px] shrink-0 border-l border-gray-200 overflow-hidden"
          style={{ height: 'calc(100vh - 64px)' }}
        >
          {selectedFunnelId && (
            <FunnelDetailPanel
              key={selectedFunnelId}
              funnelId={selectedFunnelId}
              onClose={() => setSelectedFunnelId(null)}
            />
          )}

          {selectedClassNode && (
            <ClassNodeDetailPanel
              key={selectedClassNode.id}
              classNodeId={selectedClassNode.id}
              funnelId={selectedClassNode.funnelId}
              initialTitle={selectedClassNode.title}
              initialDescription={selectedClassNode.description}
              onClose={() => setSelectedClassNode(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
