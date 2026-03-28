'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dagre from '@dagrejs/dagre';
import {
  BaseEdge,
  Background,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  getBezierPath,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  type IdeaGraphEdgePayload as IdeaGraphEdgeRecord,
  type IdeaGraphNodePayload as IdeaGraphNodeRecord,
  type IdeaGraphPayload,
} from '@/lib/idea-graph';
import {
  type ActiveIdeaGraphGenerationResponse,
  applyIdeaGraphStreamEvent,
  type IdeaGraphStreamEvent,
  type StartIdeaGraphGenerationResponse,
} from '@/lib/idea-graph-stream';
import { cn } from '@/lib/utils';

type IdeaGraphNodeType =
  | 'CLAIM'
  | 'EVIDENCE'
  | 'COUNTERARGUMENT'
  | 'REBUTTAL'
  | 'EXAMPLE'
  | 'ASSUMPTION'
  | 'DEFINITION'
  | 'QUESTION'
  | 'CONCLUSION';
type IdeaGraphEdgeType =
  | 'SUPPORTS'
  | 'ATTACKS'
  | 'REBUTS'
  | 'ELABORATES'
  | 'DEPENDS_ON'
  | 'ILLUSTRATES'
  | 'CONTRASTS_WITH';
type Direction = 'LR' | 'TB';

interface ApiErrorPayload {
  error?: string;
}

interface IdeaGraphSectionProps {
  videoId: string;
  onSeekTo: (seconds: number) => void;
  showFloatingPlayerToggle: boolean;
  floatingPlayerHidden: boolean;
  onShowFloatingPlayer: () => void;
  onFloatingCanvasBoundsChange: (rect: { top: number; left: number; width: number; height: number } | null) => void;
}

interface IdeaGraphNodeCardData {
  node: IdeaGraphNodeRecord;
  direction: Direction;
  isSelected: boolean;
  onToggleCollapse: (nodeId: string) => void;
  onStartAddChild: (nodeId: string) => void;
}

interface WrappedEdgeData {
  color: string;
  typeLabel: string;
}

const NODE_WIDTH = 280;
const NODE_HEIGHT = 140;

const NODE_TYPE_META: Record<IdeaGraphNodeType, { label: string; className: string }> = {
  CLAIM: { label: 'Claim', className: 'bg-blue-100 text-blue-700' },
  EVIDENCE: { label: 'Evidence', className: 'bg-green-100 text-green-700' },
  COUNTERARGUMENT: { label: 'Counter', className: 'bg-amber-100 text-amber-700' },
  REBUTTAL: { label: 'Rebuttal', className: 'bg-orange-100 text-orange-700' },
  EXAMPLE: { label: 'Example', className: 'bg-emerald-100 text-emerald-700' },
  ASSUMPTION: { label: 'Assumption', className: 'bg-gray-200 text-gray-700' },
  DEFINITION: { label: 'Definition', className: 'bg-cyan-100 text-cyan-700' },
  QUESTION: { label: 'Question', className: 'bg-violet-100 text-violet-700' },
  CONCLUSION: { label: 'Conclusion', className: 'bg-pink-100 text-pink-700' },
};

const EDGE_TYPE_LABELS: Record<IdeaGraphEdgeType, string> = {
  SUPPORTS: 'supports',
  ATTACKS: 'attacks',
  REBUTS: 'rebuts',
  ELABORATES: 'elaborates',
  DEPENDS_ON: 'depends on',
  ILLUSTRATES: 'illustrates',
  CONTRASTS_WITH: 'contrasts',
};

const EDGE_TYPE_COLORS: Record<IdeaGraphEdgeType, string> = {
  SUPPORTS: '#3b82f6',
  ATTACKS: '#ef4444',
  REBUTS: '#f97316',
  ELABORATES: '#8b5cf6',
  DEPENDS_ON: '#6b7280',
  ILLUSTRATES: '#10b981',
  CONTRASTS_WITH: '#14b8a6',
};

function generateClientId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().slice(0, 8)}`;
}

function hexToRgb(hex: string) {
  const normalized = hex.replace('#', '');
  const expanded = normalized.length === 3
    ? normalized.split('').map((char) => char + char).join('')
    : normalized;

  const value = Number.parseInt(expanded, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

function darkenHex(hex: string, factor: number) {
  const { r, g, b } = hexToRgb(hex);
  const clamp = (channel: number) => Math.max(0, Math.min(255, Math.round(channel * factor)));
  return `rgb(${clamp(r)}, ${clamp(g)}, ${clamp(b)})`;
}

function IdeaGraphNodeCard({ data }: NodeProps) {
  const { node, direction, isSelected, onToggleCollapse, onStartAddChild } =
    data as unknown as IdeaGraphNodeCardData;
  const meta = NODE_TYPE_META[node.type];
  const targetPos = direction === 'LR' ? Position.Left : Position.Top;
  const sourcePos = direction === 'LR' ? Position.Right : Position.Bottom;

  return (
    <div
      className={cn(
        'group relative w-[280px] rounded-2xl border bg-white p-3 shadow-sm transition-all duration-200',
        isSelected
          ? 'border-blue-400 ring-2 ring-blue-200 shadow-md'
          : 'border-gray-200 hover:-translate-y-0.5 hover:bg-gray-50 hover:shadow-lg'
      )}
    >
      <Handle type="target" position={targetPos} className="!invisible" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className={cn('inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold', meta.className)}>
            {meta.label}
          </span>
          <p className="mt-2 text-sm font-semibold leading-snug text-gray-900 line-clamp-2">
            {node.title || 'Untitled node'}
          </p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleCollapse(node.id);
          }}
          className="shrink-0 text-[10px] font-medium text-gray-400 transition-colors hover:text-gray-600"
          title={node.collapsed ? 'Expand descendants' : 'Collapse descendants'}
        >
          {node.collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>
      {node.content && (
        <p className="mt-2 text-xs leading-relaxed text-gray-600 line-clamp-4">{node.content}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-400">
        <span>{node.transcriptSources.length} source{node.transcriptSources.length === 1 ? '' : 's'}</span>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onStartAddChild(node.id);
        }}
        className={cn(
          'absolute z-10 flex h-7 w-7 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-sm transition-colors hover:bg-blue-50 hover:text-blue-600',
          direction === 'LR'
            ? 'right-[-14px] top-1/2 -translate-y-1/2'
            : 'bottom-[-14px] left-1/2 -translate-x-1/2'
        )}
        title="Add connected node"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      </button>
      <Handle type="source" position={sourcePos} className="!invisible" />
    </div>
  );
}

function WrappedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeColor = ((data as WrappedEdgeData | undefined)?.color) ?? '#9ca3af';
  const typeLabel = ((data as WrappedEdgeData | undefined)?.typeLabel) ?? '';

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={{ stroke: edgeColor, strokeWidth: 1.75 }} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-auto absolute cursor-pointer rounded-md border border-gray-200 bg-white/90 px-2 py-1 text-center text-[11px] leading-tight text-gray-500 shadow-sm backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:bg-gray-50 hover:shadow-lg"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              maxWidth: 120,
              whiteSpace: 'normal',
              wordBreak: 'break-word',
            }}
          >
            <div className="flex flex-col items-center gap-1">
              {typeLabel ? (
                <span
                  className="inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-semibold"
                  style={{
                    color: darkenHex(edgeColor, 0.7),
                  }}
                >
                  {typeLabel}
                </span>
              ) : null}
              <span>{String(label)}</span>
            </div>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const nodeTypes = { ideaNode: IdeaGraphNodeCard };
const edgeTypes = { wrappedEdge: WrappedEdge };

function computeNodeDepths(graph: IdeaGraphPayload | null): Map<string, number> {
  const depths = new Map<string, number>();
  if (!graph) return depths;

  const incomingCounts = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  for (const node of graph.nodes) {
    incomingCounts.set(node.id, 0);
  }
  for (const edge of graph.edges) {
    incomingCounts.set(edge.targetNodeId, (incomingCounts.get(edge.targetNodeId) ?? 0) + 1);
    adjacency.set(edge.sourceNodeId, [...(adjacency.get(edge.sourceNodeId) ?? []), edge.targetNodeId]);
  }

  const roots = graph.nodes
    .filter((node) => (incomingCounts.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const queue = roots.length > 0 ? roots.map((id) => ({ id, depth: 0 })) : graph.nodes.map((node) => ({ id: node.id, depth: 0 }));

  while (queue.length > 0) {
    const current = queue.shift()!;
    const existingDepth = depths.get(current.id);
    if (existingDepth !== undefined && existingDepth <= current.depth) continue;
    depths.set(current.id, current.depth);

    for (const nextId of adjacency.get(current.id) ?? []) {
      queue.push({ id: nextId, depth: current.depth + 1 });
    }
  }

  for (const node of graph.nodes) {
    if (!depths.has(node.id)) {
      depths.set(node.id, 0);
    }
  }

  return depths;
}

function buildHiddenNodeSet(
  graph: IdeaGraphPayload | null,
  nodeDepths: Map<string, number>,
  visibleDepth: number
): Set<string> {
  if (!graph) return new Set();
  const adjacency = new Map<string, string[]>();
  for (const edge of graph.edges) {
    adjacency.set(edge.sourceNodeId, [...(adjacency.get(edge.sourceNodeId) ?? []), edge.targetNodeId]);
  }

  const hidden = new Set<string>(
    graph.nodes
      .filter((node) => (nodeDepths.get(node.id) ?? 0) > visibleDepth)
      .map((node) => node.id)
  );
  const visit = (nodeId: string) => {
    for (const nextId of adjacency.get(nodeId) ?? []) {
      if (hidden.has(nextId)) continue;
      hidden.add(nextId);
      visit(nextId);
    }
  };

  for (const node of graph.nodes) {
    if (node.collapsed) visit(node.id);
  }
  return hidden;
}

function applyDagreLayout(graph: IdeaGraphPayload, direction: Direction): IdeaGraphPayload {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, nodesep: 80, ranksep: 180 });
  g.setDefaultEdgeLabel(() => ({}));

  graph.nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  graph.edges.forEach((edge) => {
    g.setEdge(edge.sourceNodeId, edge.targetNodeId);
  });

  dagre.layout(g);

  return {
    ...graph,
    nodes: graph.nodes.map((node) => {
      const pos = g.node(node.id);
      return {
        ...node,
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      };
    }),
  };
}

function buildFlowNodes(
  graph: IdeaGraphPayload | null,
  direction: Direction,
  selectedNodeId: string | null,
  hiddenNodeIds: Set<string>,
  onToggleCollapse: (nodeId: string) => void,
  onStartAddChild: (nodeId: string) => void
): Node[] {
  if (!graph) return [];
  return graph.nodes
    .filter((node) => !hiddenNodeIds.has(node.id))
    .map((node) => ({
      id: node.id,
      type: 'ideaNode',
      position: { x: node.x, y: node.y },
      data: {
        node,
        direction,
        isSelected: node.id === selectedNodeId,
        onToggleCollapse,
        onStartAddChild,
      },
    }));
}

function buildFlowEdges(graph: IdeaGraphPayload | null, hiddenNodeIds: Set<string>): Edge[] {
  if (!graph) return [];
  return graph.edges
    .filter((edge) => !hiddenNodeIds.has(edge.sourceNodeId) && !hiddenNodeIds.has(edge.targetNodeId))
    .map((edge) => ({
      id: edge.id,
      type: 'wrappedEdge',
      source: edge.sourceNodeId,
      target: edge.targetNodeId,
      label: edge.label ?? EDGE_TYPE_LABELS[edge.type],
      data: { color: EDGE_TYPE_COLORS[edge.type], typeLabel: EDGE_TYPE_LABELS[edge.type] },
      markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_TYPE_COLORS[edge.type] },
    }));
}

function isGraphUnpositioned(graph: IdeaGraphPayload | null) {
  return !!graph && graph.nodes.length > 1 && graph.nodes.every((node) => node.x === 0 && node.y === 0);
}

function isIdeaGraphPayload(value: unknown): value is IdeaGraphPayload {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<IdeaGraphPayload>;
  return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges);
}

function getMaxDepthFromGraph(graph: IdeaGraphPayload): number {
  const depths = computeNodeDepths(graph);
  return Math.max(0, ...Array.from(depths.values(), (depth) => depth));
}

function Legend({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  if (collapsed) {
    return (
      <div className="absolute bottom-4 left-4 z-10">
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 hover:border-gray-300"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          Legend
        </button>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle();
        }
      }}
      aria-label="Collapse legend"
      className="absolute bottom-4 left-4 z-10 w-64 cursor-pointer rounded-2xl border border-gray-200 bg-white/95 p-3 text-left shadow-lg backdrop-blur transition-all hover:border-gray-300 hover:bg-white hover:shadow-xl"
    >
      <div className="pointer-events-none flex w-full items-center justify-end text-left text-sm font-semibold text-gray-800">
        <svg className="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </div>
      <div className="mt-3 space-y-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Node types</p>
          {Object.entries(NODE_TYPE_META).map(([type, meta]) => (
            <div key={type} className="flex items-center gap-2 text-xs text-gray-600">
              <span className={cn('inline-flex rounded-full px-2 py-0.5 font-semibold', meta.className)}>
                {meta.label}
              </span>
              <span>{type}</span>
            </div>
          ))}
        </div>
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Edge types</p>
          {Object.entries(EDGE_TYPE_LABELS).map(([type, label]) => (
            <div key={type} className="flex items-center gap-2 text-xs text-gray-600">
              <span
                className="h-0.5 w-6 rounded-full"
                style={{ backgroundColor: EDGE_TYPE_COLORS[type as IdeaGraphEdgeType] }}
              />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DepthControls({
  visibleDepth,
  maxDepth,
  onDecrease,
  onIncrease,
}: {
  visibleDepth: number;
  maxDepth: number;
  onDecrease: () => void;
  onIncrease: () => void;
}) {
  return (
    <div className="absolute bottom-4 right-4 z-10 flex items-center gap-2">
      <button
        onClick={onDecrease}
        disabled={visibleDepth <= 0}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-lg font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
      >
        -
      </button>
      <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm">
        Depth {visibleDepth + 1}/{maxDepth + 1}
      </div>
      <button
        onClick={onIncrease}
        disabled={visibleDepth >= maxDepth}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-lg font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
      >
        +
      </button>
    </div>
  );
}

interface PendingChildDraft {
  parentNodeId: string;
  nodeType: IdeaGraphNodeType;
  edgeType: IdeaGraphEdgeType;
  title: string;
}

export function IdeaGraphSection({
  videoId,
  onSeekTo,
  showFloatingPlayerToggle,
  floatingPlayerHidden,
  onShowFloatingPlayer,
  onFloatingCanvasBoundsChange,
}: IdeaGraphSectionProps) {
  const [graph, setGraph] = useState<IdeaGraphPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>('LR');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [legendCollapsed, setLegendCollapsed] = useState(true);
  const [visibleDepth, setVisibleDepth] = useState<number | null>(null);
  const [pendingChildDraft, setPendingChildDraft] = useState<PendingChildDraft | null>(null);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(null);
  const autoArrangedRef = useRef(false);
  const canvasViewportRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reactFlowRef = useRef<ReactFlowInstance<Node, Edge> | null>(null);

  const selectedNode = graph && Array.isArray(graph.nodes)
    ? graph.nodes.find((node) => node.id === selectedNodeId) ?? null
    : null;
  const selectedEdge = graph && Array.isArray(graph.edges)
    ? graph.edges.find((edge) => edge.id === selectedEdgeId) ?? null
    : null;

  const [nodeDraft, setNodeDraft] = useState<IdeaGraphNodeRecord | null>(null);
  const [edgeDraft, setEdgeDraft] = useState<IdeaGraphEdgeRecord | null>(null);
  const isGenerationInProgress = graph?.generationStatus === 'GENERATING' || activeGenerationId !== null;

  useEffect(() => {
    setNodeDraft(selectedNode ? structuredClone(selectedNode) : null);
  }, [selectedNode]);

  useEffect(() => {
    setEdgeDraft(selectedEdge ? structuredClone(selectedEdge) : null);
  }, [selectedEdge]);

  const closeGenerationStream = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph`);
      const data = (await response.json().catch(() => null)) as IdeaGraphPayload | ApiErrorPayload | null;

      if (!response.ok) {
        setGraph(null);
        setErrorMessage(
          response.status === 401
            ? 'Sign in to save and generate a private idea graph for this video.'
            : data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
              ? data.error
              : 'Failed to load idea graph.'
        );
        return;
      }

      if (data === null) {
        setGraph(null);
        setErrorMessage(null);
        return;
      }

      if (!isIdeaGraphPayload(data)) {
        setGraph(null);
        setErrorMessage('Idea graph data was malformed.');
        return;
      }

      setGraph(data);
      setDirection(data.layoutDirection);
      setVisibleDepth(data.visibleDepth ?? getMaxDepthFromGraph(data));
      setErrorMessage(null);
      if (data.generationStatus !== 'GENERATING') {
        setActiveGenerationId(null);
        closeGenerationStream();
      }
    } finally {
      setLoading(false);
    }
  }, [closeGenerationStream, videoId]);

  const connectToGenerationStream = useCallback((generationId: string, streamUrl: string) => {
    closeGenerationStream();
    const source = new EventSource(streamUrl);
    eventSourceRef.current = source;
    setActiveGenerationId(generationId);
    setErrorMessage(null);

    const handleEvent = (rawEvent: Event) => {
      const messageEvent = rawEvent as MessageEvent<string>;
      const parsed = JSON.parse(messageEvent.data) as IdeaGraphStreamEvent;
      setGraph((currentGraph) => {
        const nextGraph = applyIdeaGraphStreamEvent(currentGraph, parsed);
        if (nextGraph) {
          setVisibleDepth(getMaxDepthFromGraph(nextGraph));
        }
        return nextGraph;
      });

      if (parsed.type === 'completed' || parsed.type === 'failed') {
        closeGenerationStream();
        setActiveGenerationId(null);
        void fetchGraph();
      }
    };

    const streamEventTypes: IdeaGraphStreamEvent['type'][] = [
      'generation_started',
      'chunk_index_ready',
      'chunk_read',
      'node_added',
      'node_updated',
      'edge_added',
      'source_attached',
      'snapshot',
      'completed',
      'failed',
    ];

    streamEventTypes.forEach((eventType) => {
      source.addEventListener(eventType, handleEvent as EventListener);
    });

    source.onerror = () => {
      if (eventSourceRef.current !== source) return;
      setErrorMessage((current) => current ?? 'Live idea graph stream disconnected. Attempting to reconnect...');
    };
    source.onopen = () => {
      setErrorMessage((current) =>
        current === 'Live idea graph stream disconnected. Attempting to reconnect...' ? null : current
      );
    };
  }, [closeGenerationStream, fetchGraph]);

  const fetchActiveGeneration = useCallback(async () => {
    const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph/generate`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = (await response.json().catch(() => null)) as ActiveIdeaGraphGenerationResponse | ApiErrorPayload | null;
    if (!response.ok) {
      throw new Error(
        data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
          ? data.error
          : 'Failed to fetch active idea graph generation.'
      );
    }
    return data as ActiveIdeaGraphGenerationResponse;
  }, [videoId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  useEffect(() => {
    if (graph?.generationStatus !== 'GENERATING') return;
    if (eventSourceRef.current || activeGenerationId) return;
    void (async () => {
      try {
        const activeGeneration = await fetchActiveGeneration();
        if (activeGeneration.active && activeGeneration.generationId && activeGeneration.eventsUrl) {
          connectToGenerationStream(activeGeneration.generationId, activeGeneration.eventsUrl);
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to reconnect to live idea graph stream.');
      }
    })();
  }, [activeGenerationId, connectToGenerationStream, fetchActiveGeneration, graph?.generationStatus]);

  useEffect(() => () => {
    closeGenerationStream();
  }, [closeGenerationStream]);

  useEffect(() => {
    const element = canvasViewportRef.current;
    if (!element) return;

    const updateBounds = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.min(360, Math.max(240, rect.width * 0.3));
      const height = width * 9 / 16;
      onFloatingCanvasBoundsChange({
        top: Math.max(16, rect.bottom - height - 16),
        left: Math.max(16, rect.right - width - 16),
        width,
        height,
      });
    };

    updateBounds();
    const resizeObserver = new ResizeObserver(updateBounds);
    resizeObserver.observe(element);
    window.addEventListener('scroll', updateBounds, { passive: true });
    window.addEventListener('resize', updateBounds);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('scroll', updateBounds);
      window.removeEventListener('resize', updateBounds);
      onFloatingCanvasBoundsChange(null);
    };
  }, [onFloatingCanvasBoundsChange]);

  const persistGraph = useCallback(async (
    nextGraph: IdeaGraphPayload,
    nextDirection: Direction,
    nextVisibleDepth: number
  ) => {
    if (nextGraph.generationStatus === 'GENERATING') {
      return;
    }
    setSaving(true);
    try {
      const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layoutDirection: nextDirection,
          visibleDepth: nextVisibleDepth,
          nodes: nextGraph.nodes,
          edges: nextGraph.edges,
        }),
      });
      const saved = (await response.json().catch(() => null)) as IdeaGraphPayload | ApiErrorPayload | null;
      if (!response.ok) {
        setErrorMessage(
          saved && typeof saved === 'object' && 'error' in saved && typeof saved.error === 'string'
            ? saved.error
            : 'Failed to save idea graph.'
        );
        return;
      }
      if (saved && isIdeaGraphPayload(saved)) {
        setGraph(saved);
        setErrorMessage(null);
      }
    } finally {
      setSaving(false);
    }
  }, [videoId]);

  const displayedGraph = useMemo(
    () => (graph?.generationStatus === 'GENERATING' && graph.nodes.length > 0 ? applyDagreLayout(graph, direction) : graph),
    [graph, direction]
  );

  const nodeDepths = useMemo(() => computeNodeDepths(displayedGraph), [displayedGraph]);
  const maxVisibleDepth = useMemo(
    () => Math.max(0, ...Array.from(nodeDepths.values(), (depth) => depth)),
    [nodeDepths]
  );

  useEffect(() => {
    setVisibleDepth((current) => {
      if (current === null) return maxVisibleDepth;
      return Math.min(current, maxVisibleDepth);
    });
  }, [maxVisibleDepth]);

  const effectiveVisibleDepth = visibleDepth ?? maxVisibleDepth;
  const hiddenNodeIds = useMemo(
    () => buildHiddenNodeSet(displayedGraph, nodeDepths, effectiveVisibleDepth),
    [displayedGraph, nodeDepths, effectiveVisibleDepth]
  );

  const persistViewSettings = useCallback(async (nextDirection: Direction, nextVisibleDepth: number | null) => {
    try {
      const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layoutDirection: nextDirection,
          visibleDepth: nextVisibleDepth,
        }),
      });
      const saved = (await response.json().catch(() => null)) as IdeaGraphPayload | ApiErrorPayload | null;
      if (!response.ok) {
        setErrorMessage(
          saved && typeof saved === 'object' && 'error' in saved && typeof saved.error === 'string'
            ? saved.error
            : 'Failed to save graph view settings.'
        );
        return;
      }
      if (saved && isIdeaGraphPayload(saved)) {
        setGraph((currentGraph) =>
          currentGraph?.generationStatus === 'GENERATING'
            ? {
                ...currentGraph,
                layoutDirection: saved.layoutDirection,
                visibleDepth: saved.visibleDepth,
              }
            : saved
        );
        setErrorMessage(null);
      }
    } catch {
      setErrorMessage('Failed to save graph view settings.');
    }
  }, [videoId]);

  const handleToggleCollapse = useCallback((nodeId: string) => {
    if (!graph || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === nodeId ? { ...node, collapsed: !node.collapsed } : node
      ),
    };
    setGraph(nextGraph);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph]);

  const handleStartAddChild = useCallback((nodeId: string) => {
    if (isGenerationInProgress) return;
    setPendingChildDraft({
      parentNodeId: nodeId,
      nodeType: 'CLAIM',
      edgeType: 'SUPPORTS',
      title: '',
    });
  }, [isGenerationInProgress]);

  const flowNodes = useMemo(
    () =>
      buildFlowNodes(
        displayedGraph,
        direction,
        selectedNodeId,
        hiddenNodeIds,
        handleToggleCollapse,
        handleStartAddChild
      ),
    [displayedGraph, direction, selectedNodeId, hiddenNodeIds, handleToggleCollapse, handleStartAddChild]
  );
  const flowEdges = useMemo(() => buildFlowEdges(displayedGraph, hiddenNodeIds), [displayedGraph, hiddenNodeIds]);
  const [canvasNodes, setCanvasNodes, onCanvasNodesChange] = useNodesState(flowNodes);
  const [canvasEdges, setCanvasEdges, onCanvasEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setCanvasNodes(flowNodes);
  }, [flowNodes, setCanvasNodes]);

  useEffect(() => {
    setCanvasEdges(flowEdges);
  }, [flowEdges, setCanvasEdges]);

  useEffect(() => {
    if (!isGenerationInProgress || !reactFlowRef.current || !displayedGraph || displayedGraph.nodes.length === 0) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      reactFlowRef.current?.fitView({ padding: 0.18, duration: 300 });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [displayedGraph, isGenerationInProgress]);

  useEffect(() => {
    if (!graph || graph.generationStatus === 'GENERATING' || autoArrangedRef.current || !isGraphUnpositioned(graph)) return;
    autoArrangedRef.current = true;
    const laidOut = applyDagreLayout(graph, direction);
    setGraph(laidOut);
    void persistGraph(laidOut, direction, effectiveVisibleDepth);
  }, [graph, direction, effectiveVisibleDepth, persistGraph]);

  const handleGenerate = useCallback(async () => {
    if (isGenerationInProgress) return;
    let response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ replaceExisting: false }),
    });

    if (response.status === 409) {
      const confirmed = window.confirm(
        'Generating a new idea graph will replace the current graph. Continue?'
      );
      if (!confirmed) return;
      response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/idea-graph/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ replaceExisting: true }),
      });
    }

    if (response.ok) {
      const data = (await response.json().catch(() => null)) as StartIdeaGraphGenerationResponse | ApiErrorPayload | null;
      if (!data || !('generationId' in data) || !data.generationId || !data.eventsUrl) {
        setErrorMessage('Failed to start idea graph generation.');
        return;
      }
      autoArrangedRef.current = false;
      setErrorMessage(null);
      setGraph((currentGraph) =>
        currentGraph
          ? {
              ...currentGraph,
              generationStatus: 'GENERATING',
              generationError: null,
            }
          : currentGraph
      );
      connectToGenerationStream(data.generationId, data.eventsUrl);
    } else {
      const data = (await response.json().catch(() => null)) as ApiErrorPayload | null;
      setErrorMessage(data?.error ?? 'Failed to start idea graph generation.');
    }
  }, [connectToGenerationStream, isGenerationInProgress, videoId]);

  const handleAddNode = useCallback(() => {
    if (isGenerationInProgress) return;
    const baseGraph: IdeaGraphPayload = graph ?? {
      id: '',
      userId: '',
      videoId,
      generationStatus: 'COMPLETED',
      generationError: null,
      generatedAt: null,
      layoutDirection: direction,
      visibleDepth: effectiveVisibleDepth,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      nodes: [],
      edges: [],
    };

    const nextNode: IdeaGraphNodeRecord = {
      id: generateClientId('node'),
      type: 'CLAIM',
      title: 'New claim',
      content: '',
      x: baseGraph.nodes.length * 40,
      y: baseGraph.nodes.length * 40,
      collapsed: false,
      transcriptSources: [],
    };
    const nextGraph = {
      ...baseGraph,
      generationStatus: 'COMPLETED' as const,
      nodes: [...baseGraph.nodes, nextNode],
      edges: baseGraph.edges,
    };
    setGraph(nextGraph);
    setSelectedNodeId(nextNode.id);
    setSelectedEdgeId(null);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph, videoId]);

  const handleCreateChildNode = useCallback(() => {
    if (!graph || !pendingChildDraft || isGenerationInProgress) return;
    const parentNode = graph.nodes.find((node) => node.id === pendingChildDraft.parentNodeId);
    if (!parentNode) {
      setPendingChildDraft(null);
      return;
    }

    const newNodeId = generateClientId('node');
    const newEdgeId = generateClientId('edge');
    const defaultTitle = pendingChildDraft.title.trim() || `New ${NODE_TYPE_META[pendingChildDraft.nodeType].label}`;
    const nextNode: IdeaGraphNodeRecord = {
      id: newNodeId,
      type: pendingChildDraft.nodeType,
      title: defaultTitle,
      content: '',
      x: direction === 'LR' ? parentNode.x + NODE_WIDTH + 80 : parentNode.x,
      y: direction === 'LR' ? parentNode.y : parentNode.y + NODE_HEIGHT + 80,
      collapsed: false,
      transcriptSources: [],
    };

    const nextGraph = {
      ...graph,
      nodes: [...graph.nodes, nextNode],
      edges: [
        ...graph.edges,
        {
          id: newEdgeId,
          sourceNodeId: parentNode.id,
          targetNodeId: newNodeId,
          type: pendingChildDraft.edgeType,
          label: null,
        },
      ],
    };

    setGraph(nextGraph);
    setSelectedNodeId(newNodeId);
    setSelectedEdgeId(null);
    setPendingChildDraft(null);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, pendingChildDraft, persistGraph]);

  const handleArrange = useCallback(() => {
    if (!graph || isGenerationInProgress) return;
    const laidOut = applyDagreLayout(graph, direction);
    setGraph(laidOut);
    void persistGraph(laidOut, direction, effectiveVisibleDepth);
  }, [graph, direction, effectiveVisibleDepth, isGenerationInProgress, persistGraph]);

  const handleToggleDirection = useCallback(() => {
    if (!graph) {
      const nextDirection: Direction = direction === 'LR' ? 'TB' : 'LR';
      setDirection(nextDirection);
      void persistViewSettings(nextDirection, visibleDepth);
      return;
    }

    const nextDirection: Direction = direction === 'LR' ? 'TB' : 'LR';
    setDirection(nextDirection);
    if (isGenerationInProgress) {
      void persistViewSettings(nextDirection, visibleDepth);
      return;
    }
    const laidOut = applyDagreLayout(graph, nextDirection);
    setGraph(laidOut);
    void persistGraph(laidOut, nextDirection, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph, persistViewSettings, visibleDepth]);

  const handleConnect = useCallback((connection: Connection) => {
    if (!graph || !connection.source || !connection.target || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      edges: [
        ...graph.edges,
        {
          id: generateClientId('edge'),
          sourceNodeId: connection.source,
          targetNodeId: connection.target,
          type: 'SUPPORTS' as IdeaGraphEdgeType,
          label: null,
        },
      ],
    };
    setGraph(nextGraph);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph]);

  const handleNodeDragStop = useCallback((_event: React.MouseEvent, draggedNode: Node) => {
    if (!graph || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === draggedNode.id
          ? { ...node, x: draggedNode.position.x, y: draggedNode.position.y }
          : node
      ),
    };
    setGraph(nextGraph);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph]);

  const handleSaveNode = useCallback(() => {
    if (!graph || !nodeDraft || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      nodes: graph.nodes.map((node) => (node.id === nodeDraft.id ? nodeDraft : node)),
    };
    setGraph(nextGraph);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, nodeDraft, persistGraph]);

  const handleDeleteNode = useCallback(() => {
    if (!graph || !selectedNodeId || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      nodes: graph.nodes.filter((node) => node.id !== selectedNodeId),
      edges: graph.edges.filter(
        (edge) => edge.sourceNodeId !== selectedNodeId && edge.targetNodeId !== selectedNodeId
      ),
    };
    setGraph(nextGraph);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, selectedNodeId, persistGraph]);

  const handleSaveEdge = useCallback(() => {
    if (!graph || !edgeDraft || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      edges: graph.edges.map((edge) => (edge.id === edgeDraft.id ? edgeDraft : edge)),
    };
    setGraph(nextGraph);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, edgeDraft, graph, isGenerationInProgress, persistGraph]);

  const handleDeleteEdge = useCallback(() => {
    if (!graph || !selectedEdgeId || isGenerationInProgress) return;
    const nextGraph = {
      ...graph,
      edges: graph.edges.filter((edge) => edge.id !== selectedEdgeId),
    };
    setGraph(nextGraph);
    setSelectedEdgeId(null);
    void persistGraph(nextGraph, direction, effectiveVisibleDepth);
  }, [direction, effectiveVisibleDepth, graph, isGenerationInProgress, persistGraph, selectedEdgeId]);

  if (loading) {
    return (
      <div className="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-400 shadow-sm">
        Loading idea graph...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Idea Graph</h2>
          <p className="mt-1 text-sm text-gray-500">
            Decompose the video into claims, evidence, counterarguments, and cross-links.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerate}
            disabled={isGenerationInProgress}
            className="rounded-full border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-wait disabled:opacity-60"
          >
            {isGenerationInProgress ? 'Generating...' : 'Generate idea graph'}
          </button>
        </div>
      </div>

      {graph?.generationError && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {graph.generationError}
        </div>
      )}

      {errorMessage && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {errorMessage}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div
          ref={canvasViewportRef}
          className="relative h-[720px] overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-sm"
        >
          <div className="absolute left-4 top-4 z-10 flex items-center gap-2">
            <button
              onClick={handleArrange}
              disabled={isGenerationInProgress}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 hover:border-gray-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
              Arrange
            </button>
            <button
              onClick={handleToggleDirection}
              title={direction === 'LR' ? 'Switch to vertical layout' : 'Switch to horizontal layout'}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 hover:border-gray-300"
            >
              {direction === 'LR' ? (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12h18M3 6h18M3 18h18" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v18M6 3v18M18 3v18" />
                </svg>
              )}
              {direction === 'LR' ? 'Vertical' : 'Horizontal'}
            </button>
          </div>

          {graph && graph.nodes.length > 0 ? (
            <ReactFlowProvider>
              <ReactFlow
                onInit={(instance) => {
                  reactFlowRef.current = instance;
                }}
                nodes={canvasNodes}
                edges={canvasEdges}
                onNodesChange={onCanvasNodesChange}
                onEdgesChange={onCanvasEdgesChange}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onNodeClick={(_event, node) => {
                  setSelectedNodeId(node.id);
                  setSelectedEdgeId(null);
                }}
                onEdgeClick={(_event, edge) => {
                  setSelectedEdgeId(edge.id);
                  setSelectedNodeId(null);
                }}
                onPaneClick={() => {
                  setSelectedNodeId(null);
                  setSelectedEdgeId(null);
                }}
                onConnect={handleConnect}
                onNodeDragStop={handleNodeDragStop}
                nodesDraggable={!isGenerationInProgress}
                nodesConnectable={!isGenerationInProgress}
                fitView
                fitViewOptions={{ padding: 0.18 }}
                minZoom={0.2}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#e5e7eb" gap={20} />
                <Legend collapsed={legendCollapsed} onToggle={() => setLegendCollapsed((value) => !value)} />
              </ReactFlow>
            </ReactFlowProvider>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-gray-400">
              <p className="text-lg font-medium text-gray-500">No graph yet</p>
              <p className="max-w-md text-sm">
                Generate a full idea graph from the video transcript, or start from scratch by adding nodes.
              </p>
              <button
                onClick={handleAddNode}
                disabled={isGenerationInProgress}
                className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Add root node
              </button>
            </div>
          )}

          {showFloatingPlayerToggle && floatingPlayerHidden && (
            <button
              type="button"
              onClick={onShowFloatingPlayer}
              className="absolute bottom-4 right-4 z-20 rounded-full border border-gray-200 bg-white/95 px-3 py-2 text-sm font-medium text-gray-700 shadow-lg backdrop-blur transition-colors hover:bg-gray-50"
            >
              Show video
            </button>
          )}

          {graph && graph.nodes.length > 0 && (
            <DepthControls
              visibleDepth={effectiveVisibleDepth}
              maxDepth={maxVisibleDepth}
              onDecrease={() => {
                const nextDepth = Math.max(0, effectiveVisibleDepth - 1);
                setVisibleDepth(nextDepth);
                void persistViewSettings(direction, nextDepth);
              }}
              onIncrease={() => {
                const nextDepth = Math.min(maxVisibleDepth, effectiveVisibleDepth + 1);
                setVisibleDepth(nextDepth);
                void persistViewSettings(direction, nextDepth);
              }}
            />
          )}

          {pendingChildDraft && (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/25 px-4">
              <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
                <h3 className="text-sm font-semibold text-gray-900">Add connected node</h3>
                <p className="mt-1 text-xs text-gray-500">
                  Choose how the new node connects from the selected node.
                </p>

                <div className="mt-4 space-y-3">
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Node title</label>
                    <input
                      value={pendingChildDraft.title}
                      onChange={(e) =>
                        setPendingChildDraft((current) =>
                          current ? { ...current, title: e.target.value } : current
                        )
                      }
                      placeholder="New claim"
                      className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Node type</label>
                    <select
                      value={pendingChildDraft.nodeType}
                      onChange={(e) =>
                        setPendingChildDraft((current) =>
                          current ? { ...current, nodeType: e.target.value as IdeaGraphNodeType } : current
                        )
                      }
                      className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                    >
                      {Object.entries(NODE_TYPE_META).map(([type, meta]) => (
                        <option key={type} value={type}>
                          {meta.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Edge type</label>
                    <select
                      value={pendingChildDraft.edgeType}
                      onChange={(e) =>
                        setPendingChildDraft((current) =>
                          current ? { ...current, edgeType: e.target.value as IdeaGraphEdgeType } : current
                        )
                      }
                      className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                    >
                      {Object.entries(EDGE_TYPE_LABELS).map(([type, label]) => (
                        <option key={type} value={type}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-5 flex justify-end gap-2">
                  <button
                    onClick={() => setPendingChildDraft(null)}
                    className="rounded-xl bg-gray-100 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateChildNode}
                    className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                  >
                    Create node
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="h-[720px] overflow-y-auto rounded-3xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-gray-900">Inspector</h3>
            <span className="text-xs text-gray-400">
              {isGenerationInProgress ? 'Live generation in progress' : saving ? 'Saving...' : 'Saved automatically'}
            </span>
          </div>

          {nodeDraft && (
            <div className="mt-4 space-y-4">
              <fieldset disabled={isGenerationInProgress} className="contents">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Node type</label>
                <select
                  value={nodeDraft.type}
                  onChange={(e) =>
                    setNodeDraft((current) =>
                      current ? { ...current, type: e.target.value as IdeaGraphNodeType } : current
                    )
                  }
                  className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                >
                  {Object.entries(NODE_TYPE_META).map(([type, meta]) => (
                    <option key={type} value={type}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Title</label>
                <input
                  value={nodeDraft.title}
                  onChange={(e) =>
                    setNodeDraft((current) => (current ? { ...current, title: e.target.value } : current))
                  }
                  className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Content</label>
                <textarea
                  value={nodeDraft.content ?? ''}
                  onChange={(e) =>
                    setNodeDraft((current) =>
                      current ? { ...current, content: e.target.value || null } : current
                    )
                  }
                  rows={5}
                  className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Transcript sources</label>
                  <button
                    onClick={() =>
                      setNodeDraft((current) =>
                        current
                          ? {
                            ...current,
                            transcriptSources: [
                              ...current.transcriptSources,
                              {
                                id: generateClientId('source'),
                                paraphrase: '',
                                quote: '',
                                startSec: 0,
                                endSec: 0,
                              },
                            ],
                          }
                          : current
                      )
                    }
                    className="text-xs font-medium text-blue-600 hover:text-blue-700"
                  >
                    Add source
                  </button>
                </div>
                {nodeDraft.transcriptSources.map((source, index) => (
                  <div key={source.id} className="rounded-2xl border border-gray-200 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-gray-500">Source {index + 1}</p>
                      <button
                        onClick={() =>
                          setNodeDraft((current) =>
                            current
                              ? {
                                ...current,
                                transcriptSources: current.transcriptSources.filter(
                                  (candidate) => candidate.id !== source.id
                                ),
                              }
                              : current
                          )
                        }
                        className="text-xs text-red-500 hover:text-red-600"
                      >
                        Remove
                      </button>
                    </div>
                    <textarea
                      value={source.paraphrase ?? ''}
                      onChange={(e) =>
                        setNodeDraft((current) =>
                          current
                            ? {
                              ...current,
                              transcriptSources: current.transcriptSources.map((candidate) =>
                                candidate.id === source.id
                                  ? { ...candidate, paraphrase: e.target.value || null }
                                  : candidate
                              ),
                            }
                            : current
                        )
                      }
                      rows={2}
                      placeholder="Paraphrase"
                      className="mt-2 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                    />
                    <textarea
                      value={source.quote}
                      onChange={(e) =>
                        setNodeDraft((current) =>
                          current
                            ? {
                              ...current,
                              transcriptSources: current.transcriptSources.map((candidate) =>
                                candidate.id === source.id ? { ...candidate, quote: e.target.value } : candidate
                              ),
                            }
                            : current
                        )
                      }
                      rows={3}
                      placeholder="Quote"
                      className="mt-2 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                    />
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        value={source.startSec}
                        onChange={(e) =>
                          setNodeDraft((current) =>
                            current
                              ? {
                                ...current,
                                transcriptSources: current.transcriptSources.map((candidate) =>
                                  candidate.id === source.id
                                    ? { ...candidate, startSec: Number(e.target.value) }
                                    : candidate
                                ),
                              }
                              : current
                          )
                        }
                        className="rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                      />
                      <input
                        type="number"
                        value={source.endSec}
                        onChange={(e) =>
                          setNodeDraft((current) =>
                            current
                              ? {
                                ...current,
                                transcriptSources: current.transcriptSources.map((candidate) =>
                                  candidate.id === source.id
                                    ? { ...candidate, endSec: Number(e.target.value) }
                                    : candidate
                                ),
                              }
                              : current
                          )
                        }
                        className="rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                      />
                    </div>
                    <button
                      onClick={() => onSeekTo(source.startSec)}
                      className="mt-2 text-xs font-medium text-blue-600 hover:text-blue-700"
                    >
                      Seek video to {source.startSec.toFixed(1)}s
                    </button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSaveNode}
                  disabled={isGenerationInProgress}
                  className="flex-1 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save node
                </button>
                <button
                  onClick={handleDeleteNode}
                  disabled={isGenerationInProgress}
                  className="rounded-xl bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Delete
                </button>
              </div>
              </fieldset>
            </div>
          )}

          {!nodeDraft && edgeDraft && (
            <div className="mt-4 space-y-4">
              <fieldset disabled={isGenerationInProgress} className="contents">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Edge type</label>
                <select
                  value={edgeDraft.type}
                  onChange={(e) =>
                    setEdgeDraft((current) =>
                      current ? { ...current, type: e.target.value as IdeaGraphEdgeType } : current
                    )
                  }
                  className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                >
                  {Object.entries(EDGE_TYPE_LABELS).map(([type, label]) => (
                    <option key={type} value={type}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">Label</label>
                <input
                  value={edgeDraft.label ?? ''}
                  onChange={(e) =>
                    setEdgeDraft((current) => (current ? { ...current, label: e.target.value || null } : current))
                  }
                  className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSaveEdge}
                  disabled={isGenerationInProgress}
                  className="flex-1 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save edge
                </button>
                <button
                  onClick={handleDeleteEdge}
                  disabled={isGenerationInProgress}
                  className="rounded-xl bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Delete
                </button>
              </div>
              </fieldset>
            </div>
          )}

          {!nodeDraft && !edgeDraft && (
            <div className="mt-8 rounded-2xl border border-dashed border-gray-200 p-5 text-sm text-gray-400">
              Select a node or edge to inspect and edit it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
