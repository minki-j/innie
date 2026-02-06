import { redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { TopicListClient } from '@/components/topic/TopicListClient';

export const metadata = {
  title: 'Topics - Settings',
};

export default async function TopicsSettingsPage() {
  const session = await auth();

  if (!session?.user?.id) {
    redirect('/signin');
  }

  const topics = await prisma.topic.findMany({
    where: { userId: session.user.id },
    include: {
      _count: {
        select: { videos: true, criteria: true, keywords: true, creators: true },
      },
    },
    orderBy: { createdAt: 'desc' },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Topics</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage the topics you want to track. Each topic can have criteria, gold standards, keywords, and YouTube creators.
          </p>
        </div>
      </div>

      <TopicListClient initialTopics={topics} />
    </div>
  );
}
