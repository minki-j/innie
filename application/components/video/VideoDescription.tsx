'use client';

import { useState } from 'react';
import { formatViewCount, formatPublishedDate } from '@/lib/youtube/utils';

interface VideoDescriptionProps {
  description: string;
  publishedAt: string;
  viewCount?: string;
  summary?: string | null;
}

export function VideoDescription({ description, publishedAt, viewCount, summary }: VideoDescriptionProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const shouldTruncate = description.length > 300;
  const displayDescription = isExpanded || !shouldTruncate
    ? description
    : description.slice(0, 300) + '...';

  return (
    <div className="space-y-4">
      <div className="bg-gray-100 rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 mb-2">
          {viewCount && <span>{formatViewCount(viewCount)} views</span>}
          <span>{formatPublishedDate(publishedAt)}</span>
        </div>

        <div className="text-sm text-gray-700 whitespace-pre-wrap">
          {displayDescription}
        </div>

        {shouldTruncate && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-sm font-semibold text-gray-900 mt-2 hover:text-gray-700"
          >
            {isExpanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>

      {summary && (
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Summary</h3>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{summary}</p>
        </div>
      )}
    </div>
  );
}
