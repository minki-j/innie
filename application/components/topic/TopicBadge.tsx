import { VideoTopic } from '@/types/youtube';

// Deterministic color based on topic name
const BADGE_COLORS = [
  { bg: 'bg-blue-100', text: 'text-blue-700', dimBg: 'bg-blue-50', dimText: 'text-blue-400' },
  { bg: 'bg-emerald-100', text: 'text-emerald-700', dimBg: 'bg-emerald-50', dimText: 'text-emerald-400' },
  { bg: 'bg-violet-100', text: 'text-violet-700', dimBg: 'bg-violet-50', dimText: 'text-violet-400' },
  { bg: 'bg-amber-100', text: 'text-amber-700', dimBg: 'bg-amber-50', dimText: 'text-amber-400' },
  { bg: 'bg-rose-100', text: 'text-rose-700', dimBg: 'bg-rose-50', dimText: 'text-rose-400' },
  { bg: 'bg-cyan-100', text: 'text-cyan-700', dimBg: 'bg-cyan-50', dimText: 'text-cyan-400' },
  { bg: 'bg-orange-100', text: 'text-orange-700', dimBg: 'bg-orange-50', dimText: 'text-orange-400' },
  { bg: 'bg-indigo-100', text: 'text-indigo-700', dimBg: 'bg-indigo-50', dimText: 'text-indigo-400' },
];

function getColorForTopic(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % BADGE_COLORS.length;
  return BADGE_COLORS[index];
}

interface TopicBadgeProps {
  topic: VideoTopic;
  size?: 'sm' | 'md';
}

export function TopicBadge({ topic, size = 'sm' }: TopicBadgeProps) {
  const color = getColorForTopic(topic.name);
  const hasScore = topic.totalCriteria != null && topic.totalCriteria > 0;
  const allPassed = hasScore && topic.passedCriteria === topic.totalCriteria;

  // Dim the badge if not all criteria pass
  const bgClass = hasScore && !allPassed ? color.dimBg : color.bg;
  const textClass = hasScore && !allPassed ? color.dimText : color.text;

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full font-medium ${bgClass} ${textClass} ${size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
        }`}
    >
      {topic.name}
      {hasScore && (
        <span className="opacity-75">
          ({topic.passedCriteria}/{topic.totalCriteria})
        </span>
      )}
    </span>
  );
}

interface TopicBadgeListProps {
  topics: VideoTopic[];
  size?: 'sm' | 'md';
  max?: number;
}

export function TopicBadgeList({ topics, size = 'sm', max }: TopicBadgeListProps) {
  if (!topics || topics.length === 0) return null;

  const displayed = max ? topics.slice(0, max) : topics;
  const remaining = max ? topics.length - max : 0;

  return (
    <div className="flex flex-wrap gap-1">
      {displayed.map((topic) => (
        <TopicBadge key={topic.id} topic={topic} size={size} />
      ))}
      {remaining > 0 && (
        <span className={`inline-flex items-center rounded-full bg-gray-100 text-gray-600 font-medium ${size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
          }`}>
          +{remaining}
        </span>
      )}
    </div>
  );
}
