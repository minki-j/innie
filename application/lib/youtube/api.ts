import { google } from 'googleapis';
import type {
  YouTubeSearchResult,
  YouTubeVideoListResponse,
  YouTubeVideo,
} from '@/types/youtube';
import type {
  SearchOptions,
  VideoDetailsOptions,
  RelatedVideosOptions,
  PopularVideosOptions,
  YouTubeApiError,
} from './types';

const youtube = google.youtube({
  version: 'v3',
  auth: process.env.GOOGLE_API_KEY,
});

export class YouTubeApiClient {
  private static handleError(error: any): never {
    const apiError: YouTubeApiError = {
      code: error.code || 500,
      message: error.message || 'An error occurred while fetching data from YouTube',
      status: error.status || 'INTERNAL_ERROR',
      errors: error.errors,
    };

    console.error('YouTube API Error:', apiError);
    throw new Error(apiError.message);
  }

  static async search(options: SearchOptions): Promise<YouTubeSearchResult> {
    try {
      const response = await youtube.search.list({
        part: ['snippet'],
        q: options.q,
        type: [options.type || 'video'],
        maxResults: options.maxResults || 20,
        pageToken: options.pageToken,
        order: options.order || 'relevance',
        videoDuration: options.videoDuration,
      });

      return response.data as unknown as YouTubeSearchResult;
    } catch (error) {
      return this.handleError(error);
    }
  }

  static async getVideoDetails(options: VideoDetailsOptions): Promise<YouTubeVideoListResponse> {
    try {
      const ids = Array.isArray(options.id) ? options.id.join(',') : options.id;

      const response = await youtube.videos.list({
        part: ['snippet', 'statistics', 'contentDetails'],
        id: [ids],
      });

      return response.data as unknown as YouTubeVideoListResponse;
    } catch (error) {
      return this.handleError(error);
    }
  }

  static async getRelatedVideos(options: RelatedVideosOptions): Promise<YouTubeSearchResult> {
    try {
      const response = await youtube.search.list({
        part: ['snippet'],
        type: ['video'],
        maxResults: options.maxResults || 20,
        relatedToVideoId: options.videoId,
      } as any);

      return response.data as unknown as YouTubeSearchResult;
    } catch (error) {
      return this.handleError(error);
    }
  }

  static async getPopularVideos(options: PopularVideosOptions = {}): Promise<YouTubeVideoListResponse> {
    try {
      const response = await youtube.videos.list({
        part: ['snippet', 'statistics', 'contentDetails'],
        chart: 'mostPopular',
        regionCode: options.regionCode || 'US',
        maxResults: options.maxResults || 20,
        pageToken: options.pageToken,
      });

      return response.data as unknown as YouTubeVideoListResponse;
    } catch (error) {
      return this.handleError(error);
    }
  }

  static async getChannelDetails(channelId: string) {
    try {
      const response = await youtube.channels.list({
        part: ['snippet', 'statistics'],
        id: [channelId],
      });

      return response.data;
    } catch (error) {
      return this.handleError(error);
    }
  }
}

export const youtubeApi = YouTubeApiClient;
