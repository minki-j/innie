'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

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
  initialTitle: string;
  initialDescription: string | null;
  onClose: () => void;
}

export function ClassNodeDetailPanel({
  classNodeId,
  funnelId,
  initialTitle,
  initialDescription,
  onClose,
}: Props) {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(true);
  const [deleting, setDeleting] = useState(false);

  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState(initialDescription ?? '');
  const [savedTitle, setSavedTitle] = useState(initialTitle);
  const [savedDescription, setSavedDescription] = useState(initialDescription ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setTitle(initialTitle);
    setSavedTitle(initialTitle);
    setDescription(initialDescription ?? '');
    setSavedDescription(initialDescription ?? '');
  }, [initialTitle, initialDescription]);

  useEffect(() => {
    const textarea = descriptionRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [description]);

  const saveFields = useCallback(async (newTitle: string, newDesc: string) => {
    if (!newTitle.trim() || isSaving) return;
    const titleChanged = newTitle.trim() !== savedTitle.trim();
    const descChanged = (newDesc.trim() || null) !== (savedDescription.trim() || null);
    if (!titleChanged && !descChanged) return;

    setIsSaving(true);
    setSaved(false);
    try {
      const updates: Record<string, string | null> = {};
      if (titleChanged) updates.title = newTitle.trim();
      if (descChanged) updates.description = newDesc.trim() || null;

      const res = await fetch(`/api/class-nodes/${classNodeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        setSavedTitle(newTitle.trim());
        setSavedDescription(newDesc.trim());
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        window.dispatchEvent(
          new CustomEvent('class-node-updated', {
            detail: { classNodeId, funnelId, title: newTitle.trim(), description: newDesc.trim() || null },
          }),
        );
      }
    } finally {
      setIsSaving(false);
    }
  }, [classNodeId, funnelId, isSaving, savedTitle, savedDescription]);

  const handleBlur = () => {
    saveFields(title, description);
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      descriptionRef.current?.focus();
    }
  };

  useEffect(() => {
    setLoadingVideos(true);
    fetch(`/api/class-nodes/${classNodeId}/videos`)
      .then((r) => r.json())
      .then((data) => { setVideos(data); setLoadingVideos(false); })
      .catch(() => setLoadingVideos(false));
  }, [classNodeId]);

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
      {/* Header bar */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Class node</span>
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

      <div className="flex-1 overflow-y-auto">
        {/* Title + Description */}
        <div className="px-5 pt-5 pb-4 border-b border-gray-100 space-y-2">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={handleBlur}
              onKeyDown={handleTitleKeyDown}
              placeholder="Node title…"
              className="text-xl font-bold tracking-tight text-gray-900 bg-transparent border-0 outline-none w-full py-1 placeholder:text-gray-300 focus:ring-0 rounded-lg transition-colors hover:bg-gray-50 focus:bg-gray-50 cursor-pointer focus:cursor-text px-2"
            />
            {isSaving && <span className="text-xs text-gray-400 flex-shrink-0">Saving...</span>}
            {saved && <span className="text-xs text-green-500 flex-shrink-0">Saved</span>}
          </div>
          <textarea
            ref={descriptionRef}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={handleBlur}
            placeholder="Add a description of what this node classifies…"
            rows={1}
            className="text-sm text-gray-400 bg-transparent border-0 outline-none w-full py-1.5 placeholder:text-gray-300 focus:ring-0 rounded-lg transition-colors resize-none overflow-hidden leading-relaxed hover:bg-gray-50 focus:bg-gray-50 cursor-pointer focus:cursor-text px-2"
          />
        </div>

        {/* Videos */}
        <div className="px-5 py-5">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
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
                        {Math.round(v.confidence * 100)}% confidence
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
