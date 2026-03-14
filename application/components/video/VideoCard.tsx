import Link from 'next/link';
import Image from 'next/image';
import { YouTubeVideo } from '@/types/youtube';
import { formatViewCount, formatPublishedDate, formatDuration } from '@/lib/youtube/utils';
import { FunnelBadgeList } from '@/components/funnel/FunnelBadge';

interface VideoCardProps {
  video: YouTubeVideo;
}

export function VideoCard({ video }: VideoCardProps) {
  const thumbnailUrl = video.snippet.thumbnails.high?.url || video.snippet.thumbnails.medium?.url || video.snippet.thumbnails.default.url;
  const duration = video.contentDetails?.duration;

  return (
    <Link
      href={`/watch/${video.id}`}
      className="flex flex-col gap-3 group"
    >
      <div className="relative aspect-video rounded-xl overflow-hidden bg-gray-100">
        <Image
          src={thumbnailUrl}
          alt={video.snippet.title}
          fill
          className="object-cover group-hover:scale-105 transition-transform duration-200"
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
        />
        {duration && (
          <div className="absolute bottom-2 right-2 bg-black/80 text-white text-xs font-semibold px-1.5 py-0.5 rounded">
            {formatDuration(duration)}
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <div className="flex-shrink-0">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold text-sm">
            {video.snippet.channelTitle.charAt(0).toUpperCase()}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm line-clamp-2 text-gray-900 group-hover:text-gray-700">
            {video.snippet.title}
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            {video.snippet.channelTitle}
          </p>
          <div className="flex items-center gap-1 text-xs text-gray-600 mt-0.5">
            {video.statistics?.viewCount && (
              <>
                <span>{formatViewCount(video.statistics.viewCount)} views</span>
                <span>•</span>
              </>
            )}
            <span>{formatPublishedDate(video.snippet.publishedAt)}</span>
          </div>
          {video.funnels && video.funnels.length > 0 && (
            <div className="mt-1.5">
              <FunnelBadgeList funnels={video.funnels} max={2} />
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
