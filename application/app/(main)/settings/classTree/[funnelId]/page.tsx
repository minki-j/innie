import { notFound, redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { FunnelOverviewEditor } from '@/components/funnel/FunnelOverviewEditor';
import { FunnelPanels } from '@/components/funnel/FunnelPanels';

interface FunnelDetailPageProps {
  params: Promise<{ funnelId: string }>;
}

export async function generateMetadata({ params }: FunnelDetailPageProps) {
  const { funnelId } = await params;
  const funnel = await prisma.funnel.findUnique({
    where: { id: funnelId },
    select: { name: true },
  });

  return {
    title: funnel ? `${funnel.name} - Funnel Settings` : 'Funnel Not Found',
  };
}

export default async function FunnelDetailPage({ params }: FunnelDetailPageProps) {
  const session = await auth();

  if (!session?.user?.id) {
    redirect('/signin');
  }

  const { funnelId } = await params;

  const funnel = await prisma.funnel.findFirst({
    where: { id: funnelId, userId: session.user.id },
    include: {
      keywords: { orderBy: { createdAt: 'desc' } },
      creators: { orderBy: { createdAt: 'desc' } },
    },
  });

  if (!funnel) {
    notFound();
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-10 pb-8">
        <FunnelOverviewEditor
          funnelId={funnel.id}
          initialName={funnel.name}
          initialDescription={funnel.description}
        />
      </div>

      <FunnelPanels
        funnelId={funnel.id}
        active={funnel.active}
        pipelineIntervalHours={funnel.pipelineIntervalHours}
        lastPipelineRunAt={funnel.lastPipelineRunAt?.toISOString() ?? null}
        keywords={funnel.keywords}
        creators={funnel.creators}
      />
    </div>
  );
}
