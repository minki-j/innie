'use client';

import { useState } from 'react';

interface GoldStandard {
  id: string;
  videoUrl: string;
  title: string | null;
  isPositive: boolean;
  note: string | null;
}

interface GoldStandardsEditorProps {
  topicId: string;
  initialGoldStandards: GoldStandard[];
}

export function GoldStandardsEditor({ topicId, initialGoldStandards }: GoldStandardsEditorProps) {
  const [goldStandards, setGoldStandards] = useState<GoldStandard[]>(initialGoldStandards);
  const [isAdding, setIsAdding] = useState(false);
  const [newVideoUrl, setNewVideoUrl] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newIsPositive, setNewIsPositive] = useState(true);
  const [newNote, setNewNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const positive = goldStandards.filter((g) => g.isPositive);
  const negative = goldStandards.filter((g) => !g.isPositive);

  const handleAdd = async () => {
    if (!newVideoUrl.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/gold-standards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoUrl: newVideoUrl.trim(),
          title: newTitle.trim() || null,
          isPositive: newIsPositive,
          note: newNote.trim() || null,
        }),
      });

      if (res.ok) {
        const gs = await res.json();
        setGoldStandards((prev) => [gs, ...prev]);
        resetForm();
      }
    } catch (error) {
      console.error('Failed to add gold standard:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/topics/${topicId}/gold-standards?id=${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setGoldStandards((prev) => prev.filter((g) => g.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete gold standard:', error);
    }
  };

  const resetForm = () => {
    setNewVideoUrl('');
    setNewTitle('');
    setNewNote('');
    setIsAdding(false);
  };

  const renderEntry = (gs: GoldStandard) => (
    <div key={gs.id} className="flex items-start justify-between gap-3 py-2">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {gs.title && (
            <span className="text-sm font-medium text-gray-800 truncate">{gs.title}</span>
          )}
        </div>
        <a
          href={gs.videoUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline truncate block"
        >
          {gs.videoUrl}
        </a>
        {gs.note && (
          <p className="text-xs text-gray-500 mt-1">{gs.note}</p>
        )}
      </div>
      <button
        onClick={() => handleDelete(gs.id)}
        className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors flex-shrink-0"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Positive examples */}
      <div>
        <h4 className="text-sm font-medium text-green-700 mb-2 flex items-center gap-1.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Positive Examples ({positive.length})
        </h4>
        {positive.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {positive.map(renderEntry)}
          </div>
        ) : (
          <p className="text-xs text-gray-400">No positive examples yet.</p>
        )}
      </div>

      {/* Negative examples */}
      <div>
        <h4 className="text-sm font-medium text-red-700 mb-2 flex items-center gap-1.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          Negative Examples ({negative.length})
        </h4>
        {negative.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {negative.map(renderEntry)}
          </div>
        ) : (
          <p className="text-xs text-gray-400">No negative examples yet.</p>
        )}
      </div>

      {/* Add form */}
      {isAdding ? (
        <div className="border border-gray-300 rounded-lg p-3 bg-white space-y-3">
          <input
            type="text"
            value={newVideoUrl}
            onChange={(e) => setNewVideoUrl(e.target.value)}
            placeholder="YouTube video URL"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            autoFocus
          />
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Title (optional, for display)"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => setNewIsPositive(true)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${newIsPositive
                ? 'bg-green-100 text-green-700 ring-1 ring-green-300'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
            >
              Positive
            </button>
            <button
              onClick={() => setNewIsPositive(false)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${!newIsPositive
                ? 'bg-red-100 text-red-700 ring-1 ring-red-300'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
            >
              Negative
            </button>
          </div>
          <textarea
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            rows={2}
            placeholder="Note (optional)"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical"
          />
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={resetForm}
              className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={!newVideoUrl.trim() || isSubmitting}
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
          Add Gold Standard
        </button>
      )}
    </div>
  );
}
