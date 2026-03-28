'use client';

import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils';

declare global {
  interface Window {
    YT?: {
      Player: new (
        element: HTMLElement | string,
        options: {
          videoId: string;
          playerVars?: Record<string, string | number>;
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

export interface FloatingPlayerRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface VideoPlayerProps {
  videoId: string;
  floatingRect?: FloatingPlayerRect | null;
  onHideFloating?: () => void;
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
  { videoId, floatingRect = null, onHideFloating },
  ref
) {
  const rawId = useId();
  const playerId = useMemo(() => `youtube-player-${rawId.replace(/:/g, '-')}`, [rawId]);
  const mountRef = useRef<HTMLDivElement | null>(null);
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
      if (cancelled || !mountRef.current || !window.YT?.Player) return;

      playerRef.current?.destroy();
      playerRef.current = new window.YT.Player(playerId, {
        videoId,
        playerVars: {
          autoplay: 0,
          rel: 0,
          playsinline: 1,
        },
      });
    });

    return () => {
      cancelled = true;
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [playerId, videoId]);

  return (
    <div className="relative w-full aspect-video">
      <div
        className={cn(
          'bg-black overflow-hidden',
          floatingRect
            ? 'fixed z-50 rounded-2xl border border-white/20 shadow-2xl'
            : 'absolute inset-0 rounded-xl'
        )}
        style={
          floatingRect
            ? {
                top: floatingRect.top,
                left: floatingRect.left,
                width: floatingRect.width,
                height: floatingRect.height,
              }
            : undefined
        }
      >
        {floatingRect && onHideFloating && (
          <button
            type="button"
            onClick={onHideFloating}
            className="absolute right-2 top-2 z-10 rounded-full bg-black/70 px-2 py-1 text-[11px] font-medium text-white transition-colors hover:bg-black/85"
          >
            Hide
          </button>
        )}
        <div ref={mountRef} id={playerId} className="h-full w-full" />
      </div>
    </div>
  );
});
