export const APP_NAME = 'YouTube Clone';
export const APP_DESCRIPTION = 'A YouTube clone built with Next.js';

export const VIDEOS_PER_PAGE = 20;
export const RELATED_VIDEOS_COUNT = 20;

export const CACHE_REVALIDATION = {
  HOME_FEED: 3600, // 1 hour
  VIDEO_DETAILS: 300, // 5 minutes
  SEARCH_RESULTS: 0, // no cache
} as const;

export const ROUTES = {
  HOME: '/',
  WATCH: '/watch',
  SEARCH: '/search',
  SIGNIN: '/signin',
} as const;
