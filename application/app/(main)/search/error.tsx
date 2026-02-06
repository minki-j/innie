'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const searchParams = useSearchParams();
  const query = searchParams.get('q') || '';

  useEffect(() => {
    console.error('Search page error:', error);
  }, [error]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col items-center justify-center py-12 gap-4">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Search failed
          </h2>
          <p className="text-gray-600 mb-4">
            {query ? `Failed to search for "${query}". Please try again.` : 'Something went wrong with your search.'}
          </p>
        </div>
        <button
          onClick={() => reset()}
          className="px-6 py-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors font-medium"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
