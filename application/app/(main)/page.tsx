import { Suspense } from 'react';
import { VideoGrid } from '@/components/video/VideoGrid';
import { FunnelFilter } from '@/components/funnel/FunnelFilter';
import { getUserFunnels } from '@/lib/funnels';

interface HomeProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function Home({ searchParams }: HomeProps) {
  const params = await searchParams;

  const funnelParam = params.funnel;
  const selectedFunnelIds: string[] = Array.isArray(funnelParam)
    ? funnelParam
    : funnelParam
      ? [funnelParam]
      : [];

  const funnels = await getUserFunnels();

  const effectiveFunnelIds =
    selectedFunnelIds.length > 0
      ? selectedFunnelIds
      : funnels.map((f) => f.id);

  return (
    <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Suspense fallback={null}>
        <FunnelFilter funnels={funnels} selectedFunnelIds={selectedFunnelIds} />
      </Suspense>
      <VideoGrid
        key={effectiveFunnelIds.join(',')}
        selectedFunnelIds={effectiveFunnelIds}
      />
    </div>
  );
}
