import { VideoFunnel } from '@/types/youtube';

const BADGE_COLORS = [
  { bg: 'bg-blue-100', text: 'text-blue-700' },
  { bg: 'bg-emerald-100', text: 'text-emerald-700' },
  { bg: 'bg-violet-100', text: 'text-violet-700' },
  { bg: 'bg-amber-100', text: 'text-amber-700' },
  { bg: 'bg-rose-100', text: 'text-rose-700' },
  { bg: 'bg-cyan-100', text: 'text-cyan-700' },
  { bg: 'bg-orange-100', text: 'text-orange-700' },
  { bg: 'bg-indigo-100', text: 'text-indigo-700' },
];

function getColorForFunnel(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return BADGE_COLORS[Math.abs(hash) % BADGE_COLORS.length];
}

interface FunnelBadgeProps {
  funnel: VideoFunnel;
  size?: 'sm' | 'md';
}

export function FunnelBadge({ funnel, size = 'sm' }: FunnelBadgeProps) {
  const color = getColorForFunnel(funnel.name);
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${color.bg} ${color.text} ${
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
      }`}
    >
      {funnel.name}
    </span>
  );
}

interface FunnelBadgeListProps {
  funnels: VideoFunnel[];
  size?: 'sm' | 'md';
  max?: number;
}

export function FunnelBadgeList({ funnels, size = 'sm', max }: FunnelBadgeListProps) {
  if (!funnels || funnels.length === 0) return null;

  const displayed = max ? funnels.slice(0, max) : funnels;
  const remaining = max ? funnels.length - max : 0;

  return (
    <div className="flex flex-wrap gap-1">
      {displayed.map((funnel) => (
        <FunnelBadge key={funnel.id} funnel={funnel} size={size} />
      ))}
      {remaining > 0 && (
        <span
          className={`inline-flex items-center rounded-full bg-gray-100 text-gray-600 font-medium ${
            size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
          }`}
        >
          +{remaining}
        </span>
      )}
    </div>
  );
}
