import Link from 'next/link';
import Image from 'next/image';
import { YouTubeVideo } from '@/types/youtube';
import { formatPublishedDate, formatDuration } from '@/lib/youtube/utils';

interface RelatedVideosProps {
  videos: YouTubeVideo[];
}

export function RelatedVideos({ videos }: RelatedVideosProps) {
  if (!videos || videos.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {videos.map((video) => {
        const thumbnailUrl = video.snippet.thumbnails.medium?.url || video.snippet.thumbnails.default.url;
        const duration = video.contentDetails?.duration;

        return (
          <Link
            key={video.id}
            href={`/watch/${video.id}`}
            className="flex gap-2 group"
          >
            <div className="relative w-40 aspect-video rounded-lg overflow-hidden bg-gray-100 flex-shrink-0">
              <Image
                src={thumbnailUrl}
                alt={video.snippet.title}
                fill
                className="object-cover group-hover:scale-105 transition-transform duration-200"
                sizes="160px"
              />
              {duration && (
                <div className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] font-semibold px-1 py-0.5 rounded">
                  {formatDuration(duration)}
                </div>
              )}
            </div>

            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-sm line-clamp-2 text-gray-900 group-hover:text-gray-700">
                {video.snippet.title}
              </h3>
              <p className="text-xs text-gray-600 mt-1">
                {video.snippet.channelTitle}
              </p>
              <p className="text-xs text-gray-600">
                {formatPublishedDate(video.snippet.publishedAt)}
              </p>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
