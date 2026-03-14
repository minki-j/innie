'use client';

import { useState } from 'react';

interface FunnelKeyword {
  id: string;
  keyword: string;
}

interface KeywordsEditorProps {
  funnelId: string;
  initialKeywords: FunnelKeyword[];
}

export function KeywordsEditor({ funnelId, initialKeywords }: KeywordsEditorProps) {
  const [keywords, setKeywords] = useState<FunnelKeyword[]>(initialKeywords);
  const [newKeyword, setNewKeyword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAdd = async () => {
    if (!newKeyword.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/keywords`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: newKeyword.trim() }),
      });

      if (res.ok) {
        const kw = await res.json();
        setKeywords((prev) => [...prev, kw]);
        setNewKeyword('');
      }
    } catch (error) {
      console.error('Failed to add keyword:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/funnels/${funnelId}/keywords?id=${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setKeywords((prev) => prev.filter((k) => k.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete keyword:', error);
    }
  };

  return (
    <div className="space-y-3">
      {keywords.length === 0 && (
        <p className="text-sm text-gray-500">No keywords defined yet.</p>
      )}

      <div className="flex flex-wrap gap-2">
        {keywords.map((kw) => (
          <div
            key={kw.id}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full text-sm text-gray-700 group"
          >
            <span>{kw.keyword}</span>
            <button
              onClick={() => handleDelete(kw.id)}
              className="text-gray-400 hover:text-red-500 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={newKeyword}
          onChange={(e) => setNewKeyword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
          placeholder="Add keyword..."
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <button
          onClick={handleAdd}
          disabled={!newKeyword.trim() || isSubmitting}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Add
        </button>
      </div>
    </div>
  );
}
