import { Suspense } from 'react';
import { VideoGrid } from '@/components/video/VideoGrid';
import { TopicFilter } from '@/components/topic/TopicFilter';
import { getUserTopics } from '@/lib/topics';

interface HomeProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Home({ searchParams }: HomeProps) {
  const params = await searchParams;

  // Parse topic filter from query params
  const topicParam = params.topic;
  const selectedTopicIds: string[] = Array.isArray(topicParam)
    ? topicParam
    : topicParam
      ? [topicParam]
      : [];

  const topics = await getUserTopics();

  // When no specific topics are selected ("All Topics"), use all of the
  // user's topic IDs so we only show videos that belong to at least one topic.
  const effectiveTopicIds =
    selectedTopicIds.length > 0
      ? selectedTopicIds
      : topics.map((t) => t.id);

  return (
    <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Suspense fallback={null}>
        <TopicFilter topics={topics} selectedTopicIds={selectedTopicIds} />
      </Suspense>
      <VideoGrid
        key={effectiveTopicIds.join(',')}
        selectedTopicIds={effectiveTopicIds}
      />
    </div>
  );
}
