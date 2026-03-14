'use client';

import { useEffect, useState } from 'react';

interface VideoItem {
  id: string;
  title: string;
  channelTitle: string;
  thumbnailMedium: string;
  publishedAt: string;
  confidence: number | null;
  explanation: string | null;
}

interface Props {
  classNodeId: string;
  funnelId: string;
  initialDescription: string;
  onClose: () => void;
}

export function ClassNodeDetailPanel({ classNodeId, funnelId, initialDescription, onClose }: Props) {
  const [description, setDescription] = useState(initialDescription);
  const [editingDesc, setEditingDesc] = useState(false);
  const [savingDesc, setSavingDesc] = useState(false);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    setDescription(initialDescription);
  }, [classNodeId, initialDescription]);

  useEffect(() => {
    setLoadingVideos(true);
    fetch(`/api/class-nodes/${classNodeId}/videos`)
      .then((r) => r.json())
      .then((data) => { setVideos(data); setLoadingVideos(false); })
      .catch(() => setLoadingVideos(false));
  }, [classNodeId]);

  const handleSaveDesc = async () => {
    if (!description.trim() || savingDesc) return;
    setSavingDesc(true);
    try {
      const res = await fetch(`/api/class-nodes/${classNodeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description.trim() }),
      });
      if (res.ok) {
        setEditingDesc(false);
        window.dispatchEvent(
          new CustomEvent('class-node-updated', {
            detail: { classNodeId, funnelId, description: description.trim() },
          }),
        );
      }
    } finally {
      setSavingDesc(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Delete this class node? This cannot be undone.')) return;
    setDeleting(true);
    const res = await fetch(`/api/class-nodes/${classNodeId}`, { method: 'DELETE' });
    if (res.ok) {
      const data = await res.json();
      const deletedIds: string[] = data.deletedIds ?? [classNodeId];
      window.dispatchEvent(
        new CustomEvent('class-node-deleted', { detail: { funnelId, deletedIds } }),
      );
      onClose();
    }
    setDeleting(false);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <span className="text-sm text-gray-400">Class node</span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
            title="Delete class node"
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

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
        {/* Description */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-800">Description</h3>
            {!editingDesc && (
              <button
                onClick={() => setEditingDesc(true)}
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                Edit
              </button>
            )}
          </div>

          {editingDesc ? (
            <div className="space-y-2">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-vertical"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => { setEditingDesc(false); setDescription(initialDescription); }}
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs rounded-lg hover:bg-gray-200"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveDesc}
                  disabled={savingDesc || !description.trim()}
                  className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-700 leading-relaxed">{description || 'No description.'}</p>
          )}
        </div>

        {/* Videos */}
        <div>
          <h3 className="text-sm font-semibold text-gray-800 mb-3">
            Videos passing this node{!loadingVideos && ` (${videos.length})`}
          </h3>

          {loadingVideos && (
            <div className="text-sm text-gray-400 py-4">Loading videos…</div>
          )}

          {!loadingVideos && videos.length === 0 && (
            <p className="text-sm text-gray-400">No videos have passed this class node yet.</p>
          )}

          {!loadingVideos && videos.length > 0 && (
            <div className="space-y-2">
              {videos.map((v) => (
                <a
                  key={v.id}
                  href={`https://youtube.com/watch?v=${v.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex gap-3 group hover:bg-gray-50 rounded-lg p-1.5 -mx-1.5 transition-colors"
                >
                  <img
                    src={v.thumbnailMedium}
                    alt=""
                    className="w-24 rounded object-cover shrink-0 aspect-video"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 line-clamp-2 group-hover:text-blue-600 transition-colors">
                      {v.title}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">{v.channelTitle}</p>
                    {v.confidence !== null && (
                      <span className="text-[11px] text-green-600 mt-1 inline-block">
                        {v.confidence}% confidence
                      </span>
                    )}
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
