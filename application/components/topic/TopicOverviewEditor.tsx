'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

interface TopicOverviewEditorProps {
  topicId: string;
  initialName: string;
  initialDescription: string | null;
}

export function TopicOverviewEditor({
  topicId,
  initialName,
  initialDescription,
}: TopicOverviewEditorProps) {
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
      const res = await fetch(`/api/topics/${topicId}`, {
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
      }
    } catch (error) {
      console.error('Failed to save topic:', error);
    } finally {
      setIsSaving(false);
    }
  }, [topicId, isSaving, savedName, savedDescription]);

  // Auto-save on blur
  const handleBlur = () => {
    if (hasChanges) {
      save(name, description);
    }
  };

  // Handle Enter key on the title to move focus to description
  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      descriptionRef.current?.focus();
    }
  };

  // Auto-resize the description textarea
  useEffect(() => {
    const textarea = descriptionRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [description]);

  // Cleanup timeout on unmount
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
          placeholder="Topic name"
          className="text-3xl font-extrabold tracking-tight text-gray-900 bg-gray-50 border-0 outline-none w-full py-1 placeholder:text-gray-300 focus:ring-0 focus:bg-gray-100 rounded-lg transition-colors pl-2"
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
        placeholder="Describe what kind of content this topic should cover..."
        rows={1}
        className="text-base text-gray-400 bg-gray-50 border-0 outline-none w-full py-1.5 placeholder:text-gray-300 focus:ring-0 focus:bg-gray-100 rounded-lg transition-colors resize-none overflow-hidden pl-2 leading-relaxed"
      />
    </div>
  );
}
