'use client';

import { useState } from 'react';

interface TopicCreator {
  id: string;
  channelId: string | null;
  channelUrl: string | null;
  channelName: string | null;
  scrapeMonthsBack: number;
}

interface CreatorsEditorProps {
  topicId: string;
  initialCreators: TopicCreator[];
}

export function CreatorsEditor({ topicId, initialCreators }: CreatorsEditorProps) {
  const [creators, setCreators] = useState<TopicCreator[]>(initialCreators);
  const [isAdding, setIsAdding] = useState(false);
  const [newChannelName, setNewChannelName] = useState('');
  const [newChannelUrl, setNewChannelUrl] = useState('');
  const [newScrapeMonths, setNewScrapeMonths] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editChannelName, setEditChannelName] = useState('');
  const [editChannelUrl, setEditChannelUrl] = useState('');
  const [editScrapeMonths, setEditScrapeMonths] = useState(1);

  const handleAdd = async () => {
    if ((!newChannelName.trim() && !newChannelUrl.trim()) || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/creators`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channelName: newChannelName.trim() || null,
          channelUrl: newChannelUrl.trim() || null,
          scrapeMonthsBack: newScrapeMonths,
        }),
      });

      if (res.ok) {
        const creator = await res.json();
        setCreators((prev) => [...prev, creator]);
        setNewChannelName('');
        setNewChannelUrl('');
        setNewScrapeMonths(1);
        setIsAdding(false);
      }
    } catch (error) {
      console.error('Failed to add creator:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdate = async (id: string) => {
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/creators`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id,
          channelName: editChannelName.trim() || null,
          channelUrl: editChannelUrl.trim() || null,
          scrapeMonthsBack: editScrapeMonths,
        }),
      });

      if (res.ok) {
        const updated = await res.json();
        setCreators((prev) => prev.map((c) => (c.id === id ? updated : c)));
        setEditingId(null);
      }
    } catch (error) {
      console.error('Failed to update creator:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/topics/${topicId}/creators?id=${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setCreators((prev) => prev.filter((c) => c.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete creator:', error);
    }
  };

  const startEditing = (creator: TopicCreator) => {
    setEditingId(creator.id);
    setEditChannelName(creator.channelName ?? '');
    setEditChannelUrl(creator.channelUrl ?? '');
    setEditScrapeMonths(creator.scrapeMonthsBack);
  };

  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1);

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        Add YouTube creators whose content you want to scrape. Set how far back to go (max 12 months).
      </p>

      {creators.length === 0 && !isAdding && (
        <p className="text-sm text-gray-500">No creators added yet.</p>
      )}

      {creators.map((creator) => (
        <div key={creator.id} className="border border-gray-200 rounded-lg p-3 bg-gray-50">
          {editingId === creator.id ? (
            <div className="space-y-3">
              <input
                type="text"
                value={editChannelName}
                onChange={(e) => setEditChannelName(e.target.value)}
                placeholder="Channel name"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <input
                type="text"
                value={editChannelUrl}
                onChange={(e) => setEditChannelUrl(e.target.value)}
                placeholder="Channel URL (optional)"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-600">Scrape back:</label>
                <select
                  value={editScrapeMonths}
                  onChange={(e) => setEditScrapeMonths(Number(e.target.value))}
                  className="px-2 py-1 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {monthOptions.map((m) => (
                    <option key={m} value={m}>
                      {m} {m === 1 ? 'month' : 'months'}
                    </option>
                  ))}
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
                  onClick={() => handleUpdate(creator.id)}
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
                <p className="text-sm font-medium text-gray-800">
                  {creator.channelName || creator.channelUrl || creator.channelId || 'Unknown'}
                </p>
                {creator.channelUrl && (
                  <a
                    href={creator.channelUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline"
                  >
                    {creator.channelUrl}
                  </a>
                )}
                <p className="text-xs text-gray-400 mt-1">
                  Scraping last {creator.scrapeMonthsBack} {creator.scrapeMonthsBack === 1 ? 'month' : 'months'}
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => startEditing(creator)}
                  className="p-1.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  onClick={() => handleDelete(creator.id)}
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
          <input
            type="text"
            value={newChannelName}
            onChange={(e) => setNewChannelName(e.target.value)}
            placeholder="Channel name"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            autoFocus
          />
          <input
            type="text"
            value={newChannelUrl}
            onChange={(e) => setNewChannelUrl(e.target.value)}
            placeholder="Channel URL (optional)"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-600">Scrape back:</label>
            <select
              value={newScrapeMonths}
              onChange={(e) => setNewScrapeMonths(Number(e.target.value))}
              className="px-2 py-1 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {monthOptions.map((m) => (
                <option key={m} value={m}>
                  {m} {m === 1 ? 'month' : 'months'}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => { setIsAdding(false); setNewChannelName(''); setNewChannelUrl(''); }}
              className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={(!newChannelName.trim() && !newChannelUrl.trim()) || isSubmitting}
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
          Add Creator
        </button>
      )}
    </div>
  );
}
