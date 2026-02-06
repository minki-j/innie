'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface TopicWithCounts {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  createdAt: Date;
  _count: {
    videos: number;
    criteria: number;
    keywords: number;
    creators: number;
  };
}

interface TopicListClientProps {
  initialTopics: TopicWithCounts[];
}

export function TopicListClient({ initialTopics }: TopicListClientProps) {
  const router = useRouter();
  const [topics, setTopics] = useState(initialTopics);
  const [isCreating, setIsCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleCreate = async () => {
    if (isCreating) return;

    setIsCreating(true);
    try {
      const res = await fetch('/api/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Untitled Topic' }),
      });

      if (res.ok) {
        const topic = await res.json();
        router.push(`/settings/topics/${topic.id}`);
      }
    } catch (error) {
      console.error('Failed to create topic:', error);
      setIsCreating(false);
    }
  };

  const handleDelete = async (topicId: string) => {
    if (!confirm('Are you sure you want to delete this topic? This action cannot be undone.')) return;

    setDeletingId(topicId);
    try {
      const res = await fetch(`/api/topics/${topicId}`, { method: 'DELETE' });
      if (res.ok) {
        setTopics((prev) => prev.filter((t) => t.id !== topicId));
        router.refresh();
      }
    } catch (error) {
      console.error('Failed to delete topic:', error);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Create topic */}
      <button
        onClick={handleCreate}
        disabled={isCreating}
        className="w-full border-2 border-dashed border-gray-300 rounded-lg p-4 text-sm text-gray-500 hover:border-gray-400 hover:text-gray-600 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        {isCreating ? 'Creating...' : 'Add Topic'}
      </button>

      {/* Topic list */}
      {topics.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg font-medium">No topics yet</p>
          <p className="mt-1 text-sm">Create your first topic to start tracking content.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {topics.map((topic) => (
            <div
              key={topic.id}
              className="border border-gray-200 rounded-lg p-4 bg-white hover:border-gray-300 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <Link
                  href={`/settings/topics/${topic.id}`}
                  className="flex-1 min-w-0"
                >
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900 hover:text-blue-600 transition-colors">
                      {topic.name}
                    </h3>
                    <span
                      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                        topic.active
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {topic.active ? 'Active' : 'Paused'}
                    </span>
                  </div>
                  {topic.description && (
                    <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                      {topic.description}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400">
                    <span>{topic._count.videos} videos</span>
                    <span>{topic._count.criteria} criteria</span>
                    <span>{topic._count.keywords} keywords</span>
                    <span>{topic._count.creators} creators</span>
                  </div>
                </Link>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => handleDelete(topic.id)}
                    disabled={deletingId === topic.id}
                    className="p-2 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors disabled:opacity-50"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
