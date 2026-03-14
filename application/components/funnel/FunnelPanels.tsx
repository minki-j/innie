'use client';

import { FunnelPipelineSettings } from '@/components/funnel/FunnelPipelineSettings';
import { KeywordsEditor } from '@/components/funnel/KeywordsEditor';
import { CreatorsEditor } from '@/components/funnel/CreatorsEditor';

interface FunnelKeyword {
  id: string;
  keyword: string;
}

interface FunnelCreator {
  id: string;
  channelId: string | null;
  channelUrl: string | null;
  channelName: string | null;
  scrapeMonthsBack: number;
}

interface FunnelPanelsProps {
  funnelId: string;
  active: boolean;
  pipelineIntervalHours: number;
  lastPipelineRunAt: string | null;
  keywords: FunnelKeyword[];
  creators: FunnelCreator[];
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
      <p className="text-xs text-gray-400 mt-0.5">{description}</p>
    </div>
  );
}

export function FunnelPanels({
  funnelId,
  active,
  pipelineIntervalHours,
  lastPipelineRunAt,
  keywords,
  creators,
}: FunnelPanelsProps) {
  return (
    <div className="space-y-8">
      <div>
        <SectionHeader
          title="Keywords"
          description="Keywords used to search and discover relevant videos on YouTube."
        />
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <KeywordsEditor funnelId={funnelId} initialKeywords={keywords} />
        </div>
      </div>

      <div>
        <SectionHeader
          title="Creators"
          description="YouTube channels to scrape for relevant content."
        />
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <CreatorsEditor funnelId={funnelId} initialCreators={creators} />
        </div>
      </div>

      <div>
        <SectionHeader
          title="Pipeline"
          description="Control when and how the video discovery pipeline runs."
        />
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <FunnelPipelineSettings
            funnelId={funnelId}
            initialActive={active}
            initialIntervalHours={pipelineIntervalHours}
            lastPipelineRunAt={lastPipelineRunAt}
          />
        </div>
      </div>
    </div>
  );
}
