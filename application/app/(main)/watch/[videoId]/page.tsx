import { notFound } from 'next/navigation';
import { VideoPlayer } from '@/components/video/VideoPlayer';
import { VideoInfo } from '@/components/video/VideoInfo';
import { VideoDescription } from '@/components/video/VideoDescription';
import { VideoReviewPanel } from '@/components/video/VideoReviewPanel';
import { getVideoById, getVideos } from '@/lib/videos';

interface WatchPageProps {
  params: Promise<{
    videoId: string;
  }>;
}

export async function generateMetadata({ params }: WatchPageProps) {
  const { videoId } = await params;
  const video = await getVideoById(videoId);

  if (!video) {
    return { title: 'Video Not Found' };
  }

  return {
    title: `${video.snippet.title} - YouTube`,
    description: video.snippet.description.slice(0, 160),
  };
}

export default async function WatchPage({ params }: WatchPageProps) {
  const { videoId } = await params;
  const video = await getVideoById(videoId);

  if (!video) {
    notFound();
  }

  return (
    <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <VideoPlayer videoId={videoId} />
          <VideoInfo video={video} />
          <VideoDescription
            description={video.snippet.description}
            publishedAt={video.snippet.publishedAt}
            viewCount={video.statistics?.viewCount}
            summary={video.summary}
          />
        </div>
        <div className="lg:col-span-1">
          <VideoReviewPanel
            videoId={videoId}
            funnels={video.funnels ?? []}
          />
        </div>
      </div>
    </div>
  );
}
