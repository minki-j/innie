'use client';

import { useEffect, useRef, useState } from 'react';
import { VideoDescription } from '@/components/video/VideoDescription';
import { VideoInfo } from '@/components/video/VideoInfo';
import { IdeaGraphSection } from '@/components/video/IdeaGraphSection';
import { VideoPlayer, type FloatingPlayerRect, type VideoPlayerHandle } from '@/components/video/VideoPlayer';
import { VideoReviewPanel } from '@/components/video/VideoReviewPanel';
import { type YouTubeVideo } from '@/types/youtube';

interface WatchPageClientProps {
  video: YouTubeVideo;
  videoId: string;
}

export function WatchPageClient({ video, videoId }: WatchPageClientProps) {
  const playerRef = useRef<VideoPlayerHandle>(null);
  const playerAnchorRef = useRef<HTMLDivElement>(null);
  const graphSectionRef = useRef<HTMLElement>(null);
  const [playerInView, setPlayerInView] = useState(true);
  const [graphInView, setGraphInView] = useState(false);
  const [floatingRect, setFloatingRect] = useState<FloatingPlayerRect | null>(null);
  const [floatingHidden, setFloatingHidden] = useState(false);

  useEffect(() => {
    const playerEl = playerAnchorRef.current;
    const graphEl = graphSectionRef.current;
    if (!playerEl || !graphEl) return;

    const playerObserver = new IntersectionObserver(
      ([entry]) => setPlayerInView(entry.intersectionRatio >= 0.3),
      { threshold: 0.3 }
    );
    const graphObserver = new IntersectionObserver(
      ([entry]) => setGraphInView(entry.intersectionRatio > 0.05),
      { threshold: 0.05 }
    );

    playerObserver.observe(playerEl);
    graphObserver.observe(graphEl);

    return () => {
      playerObserver.disconnect();
      graphObserver.disconnect();
    };
  }, []);

  const showFloatingPlayer = !playerInView && graphInView && floatingRect && !floatingHidden;

  return (
    <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div ref={playerAnchorRef}>
            <VideoPlayer
              ref={playerRef}
              videoId={videoId}
              floatingRect={showFloatingPlayer ? floatingRect : null}
              onHideFloating={() => setFloatingHidden(true)}
            />
          </div>
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

      <section ref={graphSectionRef} className="mt-8">
        <IdeaGraphSection
          videoId={videoId}
          floatingPlayerHidden={floatingHidden}
          showFloatingPlayerToggle={!playerInView && graphInView}
          onShowFloatingPlayer={() => setFloatingHidden(false)}
          onFloatingCanvasBoundsChange={setFloatingRect}
          onSeekTo={(seconds) => {
            playerRef.current?.seekTo(seconds);
          }}
        />
      </section>
    </div>
  );
}
