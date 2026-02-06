'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

interface TopicFilterProps {
  topics: { id: string; name: string }[];
  selectedTopicIds: string[];
}

export function TopicFilter({ topics, selectedTopicIds }: TopicFilterProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const toggleTopic = useCallback(
    (topicId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.getAll('topic');

      if (current.includes(topicId)) {
        // Remove this topic
        params.delete('topic');
        current
          .filter((id) => id !== topicId)
          .forEach((id) => params.append('topic', id));
      } else {
        // Add this topic
        params.append('topic', topicId);
      }

      router.push(`/?${params.toString()}`);
    },
    [router, searchParams]
  );

  const clearFilter = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('topic');
    router.push(`/?${params.toString()}`);
  }, [router, searchParams]);

  if (topics.length === 0) return null;

  const isAllSelected = selectedTopicIds.length === 0;

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <button
        onClick={clearFilter}
        className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${isAllSelected
            ? 'bg-gray-900 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
      >
        All Topics
      </button>
      {topics.map((topic) => {
        const isSelected = selectedTopicIds.includes(topic.id);
        return (
          <button
            key={topic.id}
            onClick={() => toggleTopic(topic.id)}
            className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${isSelected
                ? 'bg-gray-900 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
          >
            {topic.name}
          </button>
        );
      })}
    </div>
  );
}
