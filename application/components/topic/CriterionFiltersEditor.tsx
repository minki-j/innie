'use client';

import { useEffect, useState } from 'react';

type RequiredResult = 'PASS' | 'FAIL' | 'CANNOT_TELL';

interface AncestorCriterion {
  criterion: {
    id: string;
    condition: string;
    include: boolean;
    level: string;
  };
  topicId: string;
  topicName: string;
}

interface CriterionFilter {
  id: string;
  criterionId: string;
  requiredResult: RequiredResult;
  criterion: {
    id: string;
    condition: string;
    include: boolean;
    topicId: string;
  };
}

interface Props {
  topicId: string;
}

const RESULT_LABELS: Record<RequiredResult, string> = {
  PASS: 'Pass',
  FAIL: 'Fail',
  CANNOT_TELL: "Can't Tell",
};

const RESULT_COLORS: Record<RequiredResult, string> = {
  PASS: 'bg-green-100 text-green-700',
  FAIL: 'bg-red-100 text-red-700',
  CANNOT_TELL: 'bg-yellow-100 text-yellow-700',
};

export function CriterionFiltersEditor({ topicId }: Props) {
  const [filters, setFilters] = useState<CriterionFilter[]>([]);
  const [ancestorCriteria, setAncestorCriteria] = useState<AncestorCriterion[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingCriterionId, setAddingCriterionId] = useState<string | null>(null);
  const [addingResult, setAddingResult] = useState<RequiredResult>('PASS');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const [filtersRes, ancestorRes] = await Promise.all([
        fetch(`/api/topics/${topicId}/criterion-filters`),
        fetch(`/api/topics/${topicId}/ancestor-criteria`),
      ]);
      if (filtersRes.ok) setFilters(await filtersRes.json());
      if (ancestorRes.ok) setAncestorCriteria(await ancestorRes.json());
      setLoading(false);
    };
    load();
  }, [topicId]);

  const filteredCriterionIds = new Set(filters.map((f) => f.criterionId));
  const availableCriteria = ancestorCriteria.filter(
    (ac) => !filteredCriterionIds.has(ac.criterion.id),
  );

  const handleAdd = async () => {
    if (!addingCriterionId) return;
    setSaving(true);
    const res = await fetch(`/api/topics/${topicId}/criterion-filters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ criterionId: addingCriterionId, requiredResult: addingResult }),
    });
    if (res.ok) {
      const filter = await res.json();
      setFilters((prev) => [...prev, filter]);
      setAddingCriterionId(null);
      setAddingResult('PASS');
    }
    setSaving(false);
  };

  const handleDelete = async (filterId: string) => {
    setDeletingId(filterId);
    const res = await fetch(
      `/api/topics/${topicId}/criterion-filters/${filterId}`,
      { method: 'DELETE' },
    );
    if (res.ok) {
      setFilters((prev) => prev.filter((f) => f.id !== filterId));
    }
    setDeletingId(null);
  };

  // Group ancestor criteria by topic
  const grouped = ancestorCriteria.reduce<Record<string, { topicName: string; criteria: AncestorCriterion[] }>>(
    (acc, ac) => {
      if (!acc[ac.topicId]) acc[ac.topicId] = { topicName: ac.topicName, criteria: [] };
      acc[ac.topicId].criteria.push(ac);
      return acc;
    },
    {},
  );

  if (loading) {
    return (
      <div className="py-8 text-center text-sm text-gray-400">Loading filters…</div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Explanation */}
      <div className="text-sm text-gray-500 bg-blue-50 border border-blue-100 rounded-lg p-3">
        Videos enter this node when <strong>all</strong> of the filters below match. Filters reference criteria evaluated by the parent (or any ancestor) node.
      </div>

      {/* Current filters */}
      {filters.length === 0 ? (
        <p className="text-sm text-gray-400 italic">No filters yet — this node will inherit all videos from its parent.</p>
      ) : (
        <div className="space-y-2">
          {filters.map((f) => (
            <div key={f.id} className="flex items-center gap-3 p-2.5 bg-gray-50 rounded-lg border border-gray-200">
              <span
                className={`shrink-0 px-2 py-0.5 rounded text-xs font-semibold ${RESULT_COLORS[f.requiredResult]}`}
              >
                {RESULT_LABELS[f.requiredResult]}
              </span>
              <span className="flex-1 text-sm text-gray-700 truncate" title={f.criterion.condition}>
                {f.criterion.condition}
              </span>
              <button
                onClick={() => handleDelete(f.id)}
                disabled={deletingId === f.id}
                className="shrink-0 p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add filter */}
      {availableCriteria.length > 0 ? (
        <div className="border border-dashed border-gray-300 rounded-lg p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Add a filter</p>

          <div className="space-y-2">
            {/* Group by ancestor topic */}
            <select
              value={addingCriterionId ?? ''}
              onChange={(e) => setAddingCriterionId(e.target.value || null)}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— Select a criterion —</option>
              {Object.values(grouped).map(({ topicName, criteria }) => (
                <optgroup key={topicName} label={`From: ${topicName}`}>
                  {criteria
                    .filter((ac) => !filteredCriterionIds.has(ac.criterion.id))
                    .map((ac) => (
                      <option key={ac.criterion.id} value={ac.criterion.id}>
                        {ac.criterion.condition.length > 60
                          ? ac.criterion.condition.slice(0, 60) + '…'
                          : ac.criterion.condition}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>

            <div className="flex gap-2">
              {(['PASS', 'FAIL', 'CANNOT_TELL'] as RequiredResult[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setAddingResult(r)}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    addingResult === r
                      ? RESULT_COLORS[r] + ' border-current'
                      : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {RESULT_LABELS[r]}
                </button>
              ))}
            </div>

            <button
              onClick={handleAdd}
              disabled={!addingCriterionId || saving}
              className="w-full py-2 text-sm font-medium bg-gray-900 text-white rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? 'Adding…' : 'Add Filter'}
            </button>
          </div>
        </div>
      ) : ancestorCriteria.length === 0 ? (
        <p className="text-sm text-gray-400 italic">
          The parent topic has no criteria yet. Add criteria to the parent first.
        </p>
      ) : (
        <p className="text-sm text-gray-400 italic">All available ancestor criteria are already used as filters.</p>
      )}
    </div>
  );
}
