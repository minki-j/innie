import { NextRequest, NextResponse } from 'next/server';
import { youtubeApi } from '@/lib/youtube/api';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const query = searchParams.get('q');
    const maxResults = parseInt(searchParams.get('maxResults') || '20', 10);
    const pageToken = searchParams.get('pageToken') || undefined;
    const order = searchParams.get('order') as 'date' | 'rating' | 'relevance' | 'title' | 'videoCount' | 'viewCount' || 'relevance';

    if (!query) {
      return NextResponse.json(
        { error: 'Search query is required' },
        { status: 400 }
      );
    }

    const data = await youtubeApi.search({
      q: query,
      maxResults,
      pageToken,
      order,
      type: 'video',
    });

    return NextResponse.json(data);
  } catch (error) {
    console.error('Error searching videos:', error);
    return NextResponse.json(
      { error: 'Failed to search videos' },
      { status: 500 }
    );
  }
}
