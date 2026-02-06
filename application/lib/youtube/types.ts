export interface SearchOptions {
  q: string;
  maxResults?: number;
  pageToken?: string;
  order?: 'date' | 'rating' | 'relevance' | 'title' | 'videoCount' | 'viewCount';
  videoDuration?: 'any' | 'long' | 'medium' | 'short';
  type?: 'video' | 'channel' | 'playlist';
}

export interface VideoDetailsOptions {
  id: string | string[];
}

export interface RelatedVideosOptions {
  videoId: string;
  maxResults?: number;
}

export interface PopularVideosOptions {
  maxResults?: number;
  pageToken?: string;
  regionCode?: string;
}

export interface YouTubeApiError {
  code: number;
  message: string;
  status: string;
  errors?: Array<{
    domain: string;
    reason: string;
    message: string;
  }>;
}
