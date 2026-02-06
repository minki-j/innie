import { StaticVideoGrid } from '@/components/video/StaticVideoGrid';
import { youtubeApi } from '@/lib/youtube/api';

export const dynamic = 'force-dynamic';

interface SearchPageProps {
  searchParams: Promise<{
    q?: string;
    pageToken?: string;
  }>;
}

export async function generateMetadata({ searchParams }: SearchPageProps) {
  const params = await searchParams;
  const query = params.q || '';

  return {
    title: query ? `${query} - Search Results` : 'Search - YouTube',
    description: `Search results for "${query}"`,
  };
}

export default async function SearchPage({ searchParams }: SearchPageProps) {
  const params = await searchParams;
  const query = params.q || '';
  const pageToken = params.pageToken;

  if (!query) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              No search query
            </h2>
            <p className="text-gray-600">
              Please enter a search term to find videos.
            </p>
          </div>
        </div>
      </div>
    );
  }

  try {
    const searchResults = await youtubeApi.search({
      q: query,
      maxResults: 24,
      pageToken,
      type: 'video',
    });

    const videoIds = searchResults.items
      .map((item) => item.id.videoId)
      .filter((id): id is string => id !== undefined);

    if (videoIds.length === 0) {
      return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold text-gray-900">
              Search results for "{query}"
            </h1>
          </div>
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <p className="text-lg text-gray-600">No videos found</p>
            </div>
          </div>
        </div>
      );
    }

    const videoDetails = await youtubeApi.getVideoDetails({
      id: videoIds,
    });

    return (
      <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">
            Search results for "{query}"
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            {searchResults.pageInfo.totalResults.toLocaleString()} results
          </p>
        </div>

        <StaticVideoGrid videos={videoDetails.items} />
      </div>
    );
  } catch (error) {
    console.error('Search error:', error);
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              Failed to search videos
            </h2>
            <p className="text-gray-600">
              Please try again or check your search query.
            </p>
          </div>
        </div>
      </div>
    );
  }
}
