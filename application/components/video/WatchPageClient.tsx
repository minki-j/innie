'use client';

import { useRef } from 'react';
import { VideoDescription } from '@/components/video/VideoDescription';
import { VideoInfo } from '@/components/video/VideoInfo';
import { IdeaGraphSection } from '@/components/video/IdeaGraphSection';
import { VideoPlayer, type VideoPlayerHandle } from '@/components/video/VideoPlayer';
import { VideoReviewPanel } from '@/components/video/VideoReviewPanel';
import { type YouTubeVideo } from '@/types/youtube';

interface WatchPageClientProps {
  video: YouTubeVideo;
  videoId: string;
}

export function WatchPageClient({ video, videoId }: WatchPageClientProps) {
  const pagePlayerRef = useRef<VideoPlayerHandle>(null);
  const graphPlayerRef = useRef<VideoPlayerHandle>(null);

  return (
    <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <VideoPlayer ref={pagePlayerRef} videoId={videoId} />
          <VideoInfo video={video} />
          <VideoDescription
            description={video.snippet.description}
            publishedAt={video.snippet.publishedAt}
            viewCount={video.statistics?.viewCount}
            summary={video.summary}
          />
        </div>
        <div className="lg:col-span-1">
          <VideoReviewPanel videoId={videoId} funnels={video.funnels ?? []} />
        </div>
      </div>

      <section className="mt-8">
        <IdeaGraphSection
          videoId={videoId}
          videoPanel={<VideoPlayer ref={graphPlayerRef} videoId={videoId} fillContainer />}
          onSeekTo={(seconds) => {
            if (graphPlayerRef.current) {
              graphPlayerRef.current.seekTo(seconds);
              return;
            }
            pagePlayerRef.current?.seekTo(seconds);
          }}
        />
      </section>
    </div>
  );
}
