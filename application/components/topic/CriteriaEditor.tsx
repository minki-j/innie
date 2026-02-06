'use client';

import { useState } from 'react';

interface Criterion {
  id: string;
  condition: string;
  include: boolean;
  level: string;
  order: number;
}

interface CriteriaEditorProps {
  topicId: string;
  initialCriteria: Criterion[];
}

export function CriteriaEditor({ topicId, initialCriteria }: CriteriaEditorProps) {
  const [criteria, setCriteria] = useState<Criterion[]>(initialCriteria);
  const [isAdding, setIsAdding] = useState(false);
  const [newCondition, setNewCondition] = useState('');
  const [newInclude, setNewInclude] = useState(true);
  const [newLevel, setNewLevel] = useState('MUST_HAVE');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editCondition, setEditCondition] = useState('');
  const [editInclude, setEditInclude] = useState(true);
  const [editLevel, setEditLevel] = useState('MUST_HAVE');

  const handleAdd = async () => {
    if (!newCondition.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/criteria`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          condition: newCondition.trim(),
          include: newInclude,
          level: newLevel,
        }),
      });

      if (res.ok) {
        const criterion = await res.json();
        setCriteria((prev) => [...prev, criterion]);
        setNewCondition('');
        setNewInclude(true);
        setNewLevel('MUST_HAVE');
        setIsAdding(false);
      }
    } catch (error) {
      console.error('Failed to add criterion:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdate = async (id: string) => {
    if (!editCondition.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/criteria`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id,
          condition: editCondition.trim(),
          include: editInclude,
          level: editLevel,
        }),
      });

      if (res.ok) {
        const updated = await res.json();
        setCriteria((prev) => prev.map((c) => (c.id === id ? updated : c)));
        setEditingId(null);
      }
    } catch (error) {
      console.error('Failed to update criterion:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/topics/${topicId}/criteria?id=${id}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        setCriteria((prev) => prev.filter((c) => c.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete criterion:', error);
    }
  };

  const startEditing = (criterion: Criterion) => {
    setEditingId(criterion.id);
    setEditCondition(criterion.condition);
    setEditInclude(criterion.include);
    setEditLevel(criterion.level);
  };

  return (
    <div className="space-y-3">
      {criteria.length === 0 && !isAdding && (
        <p className="text-sm text-gray-500">No criteria defined yet.</p>
      )}

      {criteria.map((criterion) => (
        <div key={criterion.id} className="border border-gray-200 rounded-lg p-3 bg-gray-50">
          {editingId === criterion.id ? (
            <div className="space-y-3">
              <textarea
                value={editCondition}
                onChange={(e) => setEditCondition(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical"
              />
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setEditInclude(true)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${editInclude
                      ? 'bg-green-100 text-green-700 ring-1 ring-green-300'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                  >
                    Include
                  </button>
                  <button
                    onClick={() => setEditInclude(false)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${!editInclude
                      ? 'bg-red-100 text-red-700 ring-1 ring-red-300'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                  >
                    Exclude
                  </button>
                </div>
                <select
                  value={editLevel}
                  onChange={(e) => setEditLevel(e.target.value)}
                  className="px-2 py-1 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="MUST_HAVE">Must Have</option>
                  <option value="NICE_TO_HAVE">Nice to Have</option>
                </select>
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={() => setEditingId(null)}
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleUpdate(criterion.id)}
                  disabled={isSubmitting}
                  className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800">{criterion.condition}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${criterion.include
                      ? 'bg-green-100 text-green-700'
                      : 'bg-red-100 text-red-700'
                      }`}
                  >
                    {criterion.include ? 'Include' : 'Exclude'}
                  </span>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${criterion.level === 'MUST_HAVE'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-blue-100 text-blue-700'
                      }`}
                  >
                    {criterion.level === 'MUST_HAVE' ? 'Must Have' : 'Nice to Have'}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => startEditing(criterion)}
                  className="p-1.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  onClick={() => handleDelete(criterion.id)}
                  className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      ))}

      {isAdding ? (
        <div className="border border-gray-300 rounded-lg p-3 bg-white space-y-3">
          <textarea
            value={newCondition}
            onChange={(e) => setNewCondition(e.target.value)}
            rows={2}
            placeholder="e.g. The content mentions MCP integration in enterprise"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical"
            autoFocus
          />
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setNewInclude(true)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${newInclude
                  ? 'bg-green-100 text-green-700 ring-1 ring-green-300'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
              >
                Include
              </button>
              <button
                onClick={() => setNewInclude(false)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${!newInclude
                  ? 'bg-red-100 text-red-700 ring-1 ring-red-300'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
              >
                Exclude
              </button>
            </div>
            <select
              value={newLevel}
              onChange={(e) => setNewLevel(e.target.value)}
              className="px-2 py-1 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="MUST_HAVE">Must Have</option>
              <option value="NICE_TO_HAVE">Nice to Have</option>
            </select>
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => { setIsAdding(false); setNewCondition(''); }}
              className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={!newCondition.trim() || isSubmitting}
              className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? 'Adding...' : 'Add'}
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsAdding(true)}
          className="w-full border border-dashed border-gray-300 rounded-lg py-2.5 text-xs text-gray-500 hover:border-gray-400 hover:text-gray-600 transition-colors flex items-center justify-center gap-1.5"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Criterion
        </button>
      )}
    </div>
  );
}
