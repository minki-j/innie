'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

interface FunnelFilterProps {
  funnels: { id: string; name: string }[];
  selectedFunnelIds: string[];
}

export function FunnelFilter({ funnels, selectedFunnelIds }: FunnelFilterProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const toggleFunnel = useCallback(
    (funnelId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.getAll('funnel');

      if (current.includes(funnelId)) {
        params.delete('funnel');
        current.filter((id) => id !== funnelId).forEach((id) => params.append('funnel', id));
      } else {
        params.append('funnel', funnelId);
      }

      router.push(`/?${params.toString()}`);
    },
    [router, searchParams]
  );

  const clearFilter = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('funnel');
    router.push(`/?${params.toString()}`);
  }, [router, searchParams]);

  if (funnels.length === 0) return null;

  const isAllSelected = selectedFunnelIds.length === 0;

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <button
        onClick={clearFilter}
        className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
          isAllSelected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
      >
        All Funnels
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
  );
}
