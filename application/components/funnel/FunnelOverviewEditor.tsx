'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

interface FunnelOverviewEditorProps {
  funnelId: string;
  initialName: string;
  initialDescription: string | null;
}

export function FunnelOverviewEditor({
  funnelId,
  initialName,
  initialDescription,
}: FunnelOverviewEditorProps) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [savedName, setSavedName] = useState(initialName);
  const [savedDescription, setSavedDescription] = useState(initialDescription ?? '');
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasChanges = name !== savedName || description !== savedDescription;

  const save = useCallback(async (newName: string, newDesc: string) => {
    if (!newName.trim() || isSaving) return;
    if (newName === savedName && newDesc === savedDescription) return;

    setIsSaving(true);
    setSaved(false);
    try {
      const res = await fetch(`/api/funnels/${funnelId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName.trim(),
          description: newDesc.trim() || null,
        }),
      });

      if (res.ok) {
        setSavedName(newName.trim());
        setSavedDescription(newDesc.trim());
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);

        window.dispatchEvent(
          new CustomEvent('funnel-updated', {
            detail: { funnel: { id: funnelId, name: newName.trim() } },
          })
        );
      }
    } catch (error) {
      console.error('Failed to save funnel:', error);
    } finally {
      setIsSaving(false);
    }
  }, [funnelId, isSaving, savedName, savedDescription]);

  const handleBlur = () => {
    if (hasChanges) {
      save(name, description);
    }
  };

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      descriptionRef.current?.focus();
    }
  };

  useEffect(() => {
    const textarea = descriptionRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [description]);

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    };
  }, []);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleNameKeyDown}
          placeholder="Funnel name"
          className="text-3xl font-extrabold tracking-tight text-gray-900 bg-transparent border-0 outline-none w-full py-1 placeholder:text-gray-300 focus:ring-0 rounded-lg transition-colors hover:bg-gray-50 focus:bg-gray-50 cursor-pointer focus:cursor-text px-2"
        />
        {isSaving && (
          <span className="text-xs text-gray-400 flex-shrink-0">Saving...</span>
        )}
        {saved && (
          <span className="text-xs text-green-500 flex-shrink-0">Saved</span>
        )}
      </div>
      <textarea
        ref={descriptionRef}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onBlur={handleBlur}
        placeholder="Describe what kind of content this funnel should cover..."
        rows={1}
        className="text-base text-gray-400 bg-transparent border-0 outline-none w-full py-1.5 placeholder:text-gray-300 focus:ring-0 rounded-lg transition-colors resize-none overflow-hidden leading-relaxed hover:bg-gray-50 focus:bg-gray-50 cursor-pointer focus:cursor-text px-2"
      />
    </div>
  );
}
