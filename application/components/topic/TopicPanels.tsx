'use client';

import { useState } from 'react';
import { TopicPipelineSettings } from '@/components/topic/TopicPipelineSettings';
import { CriteriaEditor } from '@/components/topic/CriteriaEditor';
import { GoldStandardsEditor } from '@/components/topic/GoldStandardsEditor';
import { KeywordsEditor } from '@/components/topic/KeywordsEditor';
import { CreatorsEditor } from '@/components/topic/CreatorsEditor';
import { TopicVideosEditor } from '@/components/topic/TopicVideosEditor';
import { TrainingSection } from '@/components/topic/TrainingSection';
import { CriterionFiltersEditor } from '@/components/topic/CriterionFiltersEditor';

interface Criterion {
  id: string;
  condition: string;
  include: boolean;
  level: string;
  order: number;
}

interface GoldStandard {
  id: string;
  videoUrl: string;
  title: string | null;
  isPositive: boolean;
  note: string | null;
}

interface TopicKeyword {
  id: string;
  keyword: string;
}

interface TopicCreator {
  id: string;
  channelId: string | null;
  channelUrl: string | null;
  channelName: string | null;
  scrapeMonthsBack: number;
}

interface TopicPanelsProps {
  topicId: string;
  isRoot: boolean;
  active: boolean;
  pipelineIntervalHours: number;
  lastPipelineRunAt: string | null;
  criteria: Criterion[];
  goldStandards: GoldStandard[];
  keywords: TopicKeyword[];
  creators: TopicCreator[];
}

const ALL_TABS = [
  {
    id: 'classification',
    label: 'Classification',
    rootOnly: false,
    childOnly: true,
    description: 'Define which videos from the parent node enter this node by setting criterion filter rules.',
  },
  {
    id: 'criteria',
    label: 'Criteria',
    rootOnly: false,
    childOnly: false,
    description: 'Define conditions that determine if a video matches this topic.',
  },
  {
    id: 'gold-standards',
    label: 'Gold Standards',
    rootOnly: false,
    childOnly: false,
    description: 'Reference videos that exemplify what this topic should or should not include.',
  },
  {
    id: 'keywords',
    label: 'Keywords',
    rootOnly: true,
    childOnly: false,
    description: 'Keywords used to search and discover relevant videos on YouTube.',
  },
  {
    id: 'creators',
    label: 'Creators',
    rootOnly: true,
    childOnly: false,
    description: 'YouTube channels to scrape for relevant content.',
  },
  {
    id: 'videos',
    label: 'Videos',
    rootOnly: false,
    childOnly: false,
    description: 'All videos processed for this topic.',
  },
  {
    id: 'pipeline',
    label: 'Pipeline',
    rootOnly: true,
    childOnly: false,
    description: 'Control when and how the video discovery pipeline runs.',
  },
  {
    id: 'training',
    label: 'Training',
    rootOnly: false,
    childOnly: false,
    description: "Use your feedback to fine-tune innie's understanding of this topic.",
  },
] as const;

type TabId = (typeof ALL_TABS)[number]['id'];

export function TopicPanels({
  topicId,
  isRoot,
  active,
  pipelineIntervalHours,
  lastPipelineRunAt,
  criteria,
  goldStandards,
  keywords,
  creators,
}: TopicPanelsProps) {
  const visibleTabs = ALL_TABS.filter((t) => {
    if (t.rootOnly && !isRoot) return false;
    if (t.childOnly && isRoot) return false;
    return true;
  });

  const defaultTab = isRoot ? 'criteria' : 'classification';
  const [activeTab, setActiveTab] = useState<TabId>(defaultTab);

  // Ensure activeTab is always visible (e.g. when switching topics)
  const effectiveTab = visibleTabs.find((t) => t.id === activeTab)
    ? activeTab
    : (defaultTab as TabId);

  const activeTabMeta = visibleTabs.find((t) => t.id === effectiveTab)!;

  return (
    <div>
      {/* Tab bar */}
      <div className="flex gap-1 flex-wrap">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              effectiveTab === tab.id
                ? 'bg-gray-900 text-white'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100 cursor-pointer'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active panel */}
      <div className="mt-6">
        <p className="text-sm text-gray-500 mb-4">{activeTabMeta.description}</p>
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          {effectiveTab === 'classification' && (
            <CriterionFiltersEditor topicId={topicId} />
          )}
          {effectiveTab === 'criteria' && (
            <CriteriaEditor topicId={topicId} initialCriteria={criteria} />
          )}
          {effectiveTab === 'gold-standards' && (
            <GoldStandardsEditor topicId={topicId} initialGoldStandards={goldStandards} />
          )}
          {effectiveTab === 'keywords' && (
            <KeywordsEditor topicId={topicId} initialKeywords={keywords} />
          )}
          {effectiveTab === 'creators' && (
            <CreatorsEditor topicId={topicId} initialCreators={creators} />
          )}
          {effectiveTab === 'videos' && <TopicVideosEditor topicId={topicId} />}
          {effectiveTab === 'pipeline' && (
            <TopicPipelineSettings
              topicId={topicId}
              initialActive={active}
              initialIntervalHours={pipelineIntervalHours}
              lastPipelineRunAt={lastPipelineRunAt}
            />
          )}
          {effectiveTab === 'training' && <TrainingSection topicId={topicId} />}
        </div>
      </div>
    </div>
  );
}
