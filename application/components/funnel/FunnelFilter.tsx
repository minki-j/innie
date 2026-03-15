'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

interface ClassNodeItem {
  id: string;
  title: string;
}

interface FunnelItem {
  id: string;
  name: string;
  classNodes: ClassNodeItem[];
}

interface FunnelFilterProps {
  funnels: FunnelItem[];
  selectedFunnelIds: string[];
  selectedClassNodeIds: string[];
}

export function FunnelFilter({ funnels, selectedFunnelIds, selectedClassNodeIds }: FunnelFilterProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const toggleFunnel = useCallback(
    (funnelId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.getAll('funnel');

      if (current.includes(funnelId)) {
        params.delete('funnel');
        current.filter((id) => id !== funnelId).forEach((id) => params.append('funnel', id));

        // Clear class node selections that belong to this funnel
        const funnel = funnels.find((f) => f.id === funnelId);
        if (funnel) {
          const removedNodeIds = new Set(funnel.classNodes.map((n) => n.id));
          const currentNodes = params.getAll('classNode');
          params.delete('classNode');
          currentNodes
            .filter((id) => !removedNodeIds.has(id))
            .forEach((id) => params.append('classNode', id));
        }
      } else {
        params.append('funnel', funnelId);
      }

      router.push(`/?${params.toString()}`);
    },
    [router, searchParams, funnels]
  );

  const toggleClassNode = useCallback(
    (nodeId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.getAll('classNode');

      if (current.includes(nodeId)) {
        params.delete('classNode');
        current.filter((id) => id !== nodeId).forEach((id) => params.append('classNode', id));
      } else {
        params.append('classNode', nodeId);
      }

      router.push(`/?${params.toString()}`);
    },
    [router, searchParams]
  );

  const clearFilter = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('funnel');
    params.delete('classNode');
    router.push(`/?${params.toString()}`);
  }, [router, searchParams]);

  if (funnels.length === 0) return null;

  const isAllSelected = selectedFunnelIds.length === 0;
  const activeFunnels = funnels.filter((f) => selectedFunnelIds.includes(f.id));
  const activeFunnelsWithNodes = activeFunnels.filter((f) => f.classNodes.length > 0);

  return (
    <div className="flex flex-col gap-2 mb-6">
      {/* Funnel pills */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={clearFilter}
          className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
            isAllSelected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          All Topics
        </button>
        {funnels.map((funnel) => {
          const isSelected = selectedFunnelIds.includes(funnel.id);
          return (
            <button
              key={funnel.id}
              onClick={() => toggleFunnel(funnel.id)}
              className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                isSelected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {funnel.name}
            </button>
          );
        })}
      </div>

      {/* Class node sub-filters for selected funnels */}
      {activeFunnelsWithNodes.map((funnel) => (
        <div key={funnel.id} className="flex flex-wrap items-center gap-2 pl-3 border-l-2 border-gray-200">
          <span className="text-xs text-gray-400 font-medium mr-1">{funnel.name}</span>
          {funnel.classNodes.map((node) => {
            const isNodeSelected = selectedClassNodeIds.includes(node.id);
            return (
              <button
                key={node.id}
                onClick={() => toggleClassNode(node.id)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  isNodeSelected
                    ? 'bg-gray-700 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {node.title}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
