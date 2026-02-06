import { YouTubeVideo } from '@/types/youtube';
import { formatViewCount } from '@/lib/youtube/utils';
import { TopicBadgeList } from '@/components/topic/TopicBadge';

interface VideoInfoProps {
  video: YouTubeVideo;
}

export function VideoInfo({ video }: VideoInfoProps) {
  const { snippet, statistics } = video;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">
        {snippet.title}
      </h1>
      {video.topics && video.topics.length > 0 && (
        <TopicBadgeList topics={video.topics} size="md" />
      )}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold">
            {snippet.channelTitle.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-gray-900">{snippet.channelTitle}</p>
          </div>
        </div>

        <div className="flex items-center gap-6 text-sm text-gray-600">
          {statistics?.viewCount && (
            <div className="flex items-center gap-1">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <span>{formatViewCount(statistics.viewCount)} views</span>
            </div>
          )}
          {statistics?.likeCount && (
            <div className="flex items-center gap-1">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
              </svg>
              <span>{formatViewCount(statistics.likeCount)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
