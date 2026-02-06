'use client';

import { useState, KeyboardEvent } from 'react';

interface TopicKeyword {
  id: string;
  keyword: string;
}

interface KeywordsEditorProps {
  topicId: string;
  initialKeywords: TopicKeyword[];
}

export function KeywordsEditor({ topicId, initialKeywords }: KeywordsEditorProps) {
  const [keywords, setKeywords] = useState<TopicKeyword[]>(initialKeywords);
  const [inputValue, setInputValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAdd = async (keyword: string) => {
    const trimmed = keyword.trim();
    if (!trimmed || isSubmitting) return;

    // Check for duplicates
    if (keywords.some((k) => k.keyword.toLowerCase() === trimmed.toLowerCase())) {
      setInputValue('');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}/keywords`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: trimmed }),
      });

      if (res.ok) {
        const kw = await res.json();
        setKeywords((prev) => [...prev, kw]);
        setInputValue('');
      }
    } catch (error) {
      console.error('Failed to add keyword:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/topics/${topicId}/keywords?id=${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setKeywords((prev) => prev.filter((k) => k.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete keyword:', error);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      handleAdd(inputValue);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        These keywords will be used to search for videos on YouTube.
      </p>

      {/* Tags display */}
      <div className="flex flex-wrap gap-2">
        {keywords.map((kw) => (
          <span
            key={kw.id}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 rounded-full text-sm"
          >
            {kw.keyword}
            <button
              onClick={() => handleDelete(kw.id)}
              className="ml-0.5 p-0.5 rounded-full hover:bg-gray-300 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a keyword and press Enter..."
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          disabled={isSubmitting}
        />
        <button
          onClick={() => handleAdd(inputValue)}
          disabled={!inputValue.trim() || isSubmitting}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Add
        </button>
      </div>
    </div>
  );
}
