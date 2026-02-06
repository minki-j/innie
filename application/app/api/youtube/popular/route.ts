import { NextRequest, NextResponse } from 'next/server';
import { youtubeApi } from '@/lib/youtube/api';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const maxResults = parseInt(searchParams.get('maxResults') || '20', 10);
    const pageToken = searchParams.get('pageToken') || undefined;
    const regionCode = searchParams.get('regionCode') || 'US';

    const data = await youtubeApi.getPopularVideos({
      maxResults,
      pageToken,
      regionCode,
    });

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching popular videos:', error);
    return NextResponse.json(
      { error: 'Failed to fetch popular videos' },
      { status: 500 }
    );
  }
}
