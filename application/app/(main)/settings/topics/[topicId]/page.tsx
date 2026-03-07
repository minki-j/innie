import { notFound, redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { TopicOverviewEditor } from '@/components/topic/TopicOverviewEditor';
import { TopicPanels } from '@/components/topic/TopicPanels';

interface TopicDetailPageProps {
  params: Promise<{ topicId: string }>;
}

export async function generateMetadata({ params }: TopicDetailPageProps) {
  const { topicId } = await params;
  const topic = await prisma.topic.findUnique({
    where: { id: topicId },
    select: { name: true },
  });

  return {
    title: topic ? `${topic.name} - Topic Settings` : 'Topic Not Found',
  };
}

export default async function TopicDetailPage({ params }: TopicDetailPageProps) {
  const session = await auth();

  if (!session?.user?.id) {
    redirect('/signin');
  }

  const { topicId } = await params;

  const topic = await prisma.topic.findFirst({
    where: { id: topicId, userId: session.user.id },
    include: {
      criteria: { orderBy: { order: 'asc' } },
      goldStandards: { orderBy: { createdAt: 'desc' } },
      keywords: { orderBy: { createdAt: 'desc' } },
      creators: { orderBy: { createdAt: 'desc' } },
    },
  });

  if (!topic) {
    notFound();
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Editable Title & Description */}
      <div className="mb-10 pb-8">
        <TopicOverviewEditor
          topicId={topic.id}
          initialName={topic.name}
          initialDescription={topic.description}
        />
      </div>

      <TopicPanels
        topicId={topic.id}
        isRoot={!topic.parentId}
        active={topic.active}
        pipelineIntervalHours={topic.pipelineIntervalHours}
        lastPipelineRunAt={topic.lastPipelineRunAt?.toISOString() ?? null}
        criteria={topic.criteria}
        goldStandards={topic.goldStandards}
        keywords={topic.keywords}
        creators={topic.creators}
      />
    </div>
  );
}
