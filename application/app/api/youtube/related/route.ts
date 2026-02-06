import { NextRequest, NextResponse } from 'next/server';
import { youtubeApi } from '@/lib/youtube/api';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const videoId = searchParams.get('videoId');
    const maxResults = parseInt(searchParams.get('maxResults') || '20', 10);

    if (!videoId) {
      return NextResponse.json(
        { error: 'Video ID is required' },
        { status: 400 }
      );
    }

    const data = await youtubeApi.getRelatedVideos({
      videoId,
      maxResults,
    });

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching related videos:', error);
    return NextResponse.json(
      { error: 'Failed to fetch related videos' },
      { status: 500 }
    );
  }
}
