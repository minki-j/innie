'use client';

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { cn } from '@/lib/utils';

declare global {
  interface Window {
    YT?: {
      Player: new (
        element: HTMLElement | string,
        options: {
          videoId: string;
          height?: string | number;
          playerVars?: Record<string, string | number>;
          width?: string | number;
          events?: {
            onReady?: () => void;
          };
        }
      ) => {
        seekTo: (seconds: number, allowSeekAhead?: boolean) => void;
        playVideo: () => void;
        destroy: () => void;
      };
      ready?: (callback: () => void) => void;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

interface VideoPlayerProps {
  fillContainer?: boolean;
  videoId: string;
}

function loadYouTubeApi(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if (window.YT?.Player) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const existingScript = document.querySelector('script[data-youtube-iframe-api="true"]');
    if (!existingScript) {
      const script = document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      script.async = true;
      script.dataset.youtubeIframeApi = 'true';
      document.body.appendChild(script);
    }

    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };

    if (window.YT?.ready) {
      window.YT.ready(() => resolve());
    }
  });
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(function VideoPlayer(
  { videoId, fillContainer = false },
  ref
) {
  const playerHostRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<{
    seekTo: (seconds: number, allowSeekAhead?: boolean) => void;
    playVideo: () => void;
    destroy: () => void;
  } | null>(null);

  useImperativeHandle(ref, () => ({
    seekTo(seconds: number) {
      playerRef.current?.seekTo(seconds, true);
      playerRef.current?.playVideo();
    },
  }));

  useEffect(() => {
    let cancelled = false;

    loadYouTubeApi().then(() => {
      if (cancelled || !playerHostRef.current || !window.YT?.Player) return;

      const host = playerHostRef.current;
      const mountNode = document.createElement('div');
      mountNode.className = 'h-full w-full';
      host.replaceChildren(mountNode);

      playerRef.current?.destroy();
      playerRef.current = new window.YT.Player(mountNode, {
        height: '100%',
        videoId,
        playerVars: {
          autoplay: 0,
          rel: 0,
          playsinline: 1,
        },
        width: '100%',
      });
    });

    return () => {
      cancelled = true;
      playerRef.current?.destroy();
      playerRef.current = null;
      playerHostRef.current?.replaceChildren();
    };
  }, [videoId]);

  return (
    <div className={cn('relative w-full', fillContainer ? 'h-full min-h-0' : 'aspect-video')}>
      <div className={cn('absolute inset-0 overflow-hidden bg-black', fillContainer ? 'rounded-none' : 'rounded-xl')}>
        <div ref={playerHostRef} className="h-full w-full" />
      </div>
    </div>
  );
});
