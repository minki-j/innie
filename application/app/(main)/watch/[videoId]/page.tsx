import { notFound } from 'next/navigation';
import { WatchPageClient } from '@/components/video/WatchPageClient';
import { getVideoById } from '@/lib/videos';

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

  return <WatchPageClient video={video} videoId={videoId} />;
}
