import { notFound, redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { TopicOverviewEditor } from '@/components/topic/TopicOverviewEditor';
import { TopicPipelineSettings } from '@/components/topic/TopicPipelineSettings';
import { CriteriaEditor } from '@/components/topic/CriteriaEditor';
import { GoldStandardsEditor } from '@/components/topic/GoldStandardsEditor';
import { KeywordsEditor } from '@/components/topic/KeywordsEditor';
import { CreatorsEditor } from '@/components/topic/CreatorsEditor';
import { TopicVideosEditor } from '@/components/topic/TopicVideosEditor';
import { TrainingSection } from '@/components/topic/TrainingSection';

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
      <div className="mb-10 pb-8 border-b border-gray-200">
        <TopicOverviewEditor
          topicId={topic.id}
          initialName={topic.name}
          initialDescription={topic.description}
        />
      </div>

      <div className="space-y-8">

        {/* Pipeline Settings Section */}
        <section>
          <SectionHeader
            title="Pipeline Settings"
            description="Control when and how the video discovery pipeline runs for this topic."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <TopicPipelineSettings
              topicId={topic.id}
              initialActive={topic.active}
              initialIntervalHours={topic.pipelineIntervalHours}
              lastPipelineRunAt={topic.lastPipelineRunAt?.toISOString() ?? null}
            />
          </div>
        </section>

        {/* Criteria Section */}
        <section>
          <SectionHeader
            title="Criteria"
            description="Define conditions that determine if a video matches this topic. Each criterion can be marked as Include or Exclude, and prioritized as Must Have or Nice to Have."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <CriteriaEditor
              topicId={topic.id}
              initialCriteria={topic.criteria}
            />
          </div>
        </section>

        {/* Gold Standards Section */}
        <section>
          <SectionHeader
            title="Gold Standards"
            description="Reference videos that exemplify what this topic should (positive) or should not (negative) include."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <GoldStandardsEditor
              topicId={topic.id}
              initialGoldStandards={topic.goldStandards}
            />
          </div>
        </section>

        {/* Keywords Section */}
        <section>
          <SectionHeader
            title="Keywords"
            description="Keywords used to search and discover relevant videos on YouTube."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <KeywordsEditor
              topicId={topic.id}
              initialKeywords={topic.keywords}
            />
          </div>
        </section>

        {/* Creators Section */}
        <section>
          <SectionHeader
            title="YouTube Creators"
            description="YouTube channels to scrape for relevant content."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <CreatorsEditor
              topicId={topic.id}
              initialCreators={topic.creators}
            />
          </div>
        </section>

        {/* Videos Section */}
        <section>
          <SectionHeader
            title="Videos"
            description="All videos processed for this topic. Sort by criteria score or update time, and remove videos you no longer need."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <TopicVideosEditor topicId={topic.id} />
          </div>
        </section>

        {/* Training Section */}
        <section>
          <SectionHeader
            title="Train innie with my feedback"
            description="Use your feedback to fine-tune innie's understanding of this topic via RLVR training."
          />
          <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5">
            <TrainingSection topicId={topic.id} />
          </div>
        </section>
      </div>
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <p className="mt-0.5 text-sm text-gray-500">{description}</p>
    </div>
  );
}
