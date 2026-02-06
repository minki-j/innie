import { YouTubeVideo } from '@/types/youtube';
import { VideoCard } from './VideoCard';

interface StaticVideoGridProps {
  videos: YouTubeVideo[];
}

/**
 * A simple, non-paginated video grid for pages that already have
 * all their video data (e.g. search results).
 */
export function StaticVideoGrid({ videos }: StaticVideoGridProps) {
  if (!videos || videos.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <p className="text-lg text-gray-600">No videos found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-4 gap-y-8">
      {videos.map((video) => (
        <VideoCard key={video.id} video={video} />
      ))}
    </div>
  );
}
