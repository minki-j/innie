export interface Thumbnail {
  url: string;
  width: number;
  height: number;
}

export interface YouTubeVideoSnippet {
  title: string;
  description: string;
  thumbnails: {
    default: Thumbnail;
    medium: Thumbnail;
    high: Thumbnail;
    standard?: Thumbnail;
    maxres?: Thumbnail;
  };
  channelTitle: string;
  channelId: string;
  publishedAt: string;
  tags?: string[];
  categoryId?: string;
}

export interface YouTubeVideoStatistics {
  viewCount: string;
  likeCount: string;
  commentCount: string;
}

export interface YouTubeVideoContentDetails {
  duration: string; // ISO 8601 format (e.g., "PT15M33S")
  definition: string;
  caption: string;
}

export interface VideoTopic {
  id: string;
  name: string;
  passedCriteria?: number;
  totalCriteria?: number;
}

export interface YouTubeVideo {
  kind: string;
  etag: string;
  id: string;
  snippet: YouTubeVideoSnippet;
  statistics?: YouTubeVideoStatistics;
  contentDetails?: YouTubeVideoContentDetails;
  topics?: VideoTopic[];
  summary?: string | null;
}

export interface YouTubeSearchResultId {
  kind: string;
  videoId?: string;
  channelId?: string;
  playlistId?: string;
}

export interface YouTubeSearchItem {
  kind: string;
  etag: string;
  id: YouTubeSearchResultId;
  snippet: YouTubeVideoSnippet;
}

export interface PageInfo {
  totalResults: number;
  resultsPerPage: number;
}

export interface YouTubeSearchResult {
  kind: string;
  etag: string;
  nextPageToken?: string;
  prevPageToken?: string;
  regionCode?: string;
  pageInfo: PageInfo;
  items: YouTubeSearchItem[];
}

export interface YouTubeVideoListResponse {
  kind: string;
  etag: string;
  nextPageToken?: string;
  prevPageToken?: string;
  pageInfo: PageInfo;
  items: YouTubeVideo[];
}

export interface YouTubeChannel {
  kind: string;
  etag: string;
  id: string;
  snippet: {
    title: string;
    description: string;
    customUrl?: string;
    publishedAt: string;
    thumbnails: {
      default: Thumbnail;
      medium: Thumbnail;
      high: Thumbnail;
    };
  };
  statistics?: {
    viewCount: string;
    subscriberCount: string;
    videoCount: string;
  };
}

export interface YouTubeChannelListResponse {
  kind: string;
  etag: string;
  pageInfo: PageInfo;
  items: YouTubeChannel[];
}
