'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';

// ─── Types ─────────────────────────────────────────────────────────────────

export interface TopicSummary {
  id: string;
  name: string;
  description: string | null;
  parentId: string | null;
  active: boolean;
  _count: {
    videos: number;
    criteria: number;
    criterionFilters: number;
    keywords: number;
    creators: number;
  };
}

interface TopicNodeData {
  topic: TopicSummary;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
}

// ─── Dagre layout ──────────────────────────────────────────────────────────

const NODE_WIDTH = 220;
const NODE_HEIGHT = 110;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });
}

// ─── Custom Node ───────────────────────────────────────────────────────────

function TopicNodeCard({ data }: NodeProps) {
  const { topic, isSelected, onSelect, onAddChild } = data as unknown as TopicNodeData;
  const isRoot = !topic.parentId;

  return (
    <div
      className={`relative w-[220px] bg-white border-2 rounded-xl shadow-sm cursor-pointer transition-all hover:shadow-md ${
        isSelected
          ? 'border-blue-500 shadow-blue-100 shadow-md'
          : 'border-gray-200 hover:border-gray-300'
      }`}
      onClick={() => onSelect(topic.id)}
    >
      {/* Parent handle (hidden on root) */}
      {!isRoot && <Handle type="target" position={Position.Top} className="!bg-gray-300 !w-2 !h-2" />}

      <div className="p-3">
        {/* Header row */}
        <div className="flex items-center gap-2 mb-1">
          {isRoot && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-violet-100 text-violet-700 shrink-0">
              ROOT
            </span>
          )}
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
              topic.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
            }`}
          >
            {topic.active ? 'Active' : 'Paused'}
          </span>
        </div>

        {/* Topic name */}
        <p className="font-semibold text-gray-900 text-sm leading-tight line-clamp-2">
          {topic.name}
        </p>

        {/* Stats */}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-400">
          <span>{topic._count.videos} videos</span>
          <span>{topic._count.criteria} criteria</span>
          {!isRoot && topic._count.criterionFilters > 0 && (
            <span className="text-blue-400">{topic._count.criterionFilters} filters</span>
          )}
        </div>
      </div>

      {/* Add child button */}
      <button
        className="absolute -bottom-3.5 left-1/2 -translate-x-1/2 z-10 w-7 h-7 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center text-gray-400 hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-colors shadow-sm"
        onClick={(e) => {
          e.stopPropagation();
          onAddChild(topic.id);
        }}
        title="Add child topic"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
        </svg>
      </button>

      {/* Child handle */}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-300 !w-2 !h-2" />
    </div>
  );
}

const nodeTypes = { topicNode: TopicNodeCard };

// ─── Inner canvas (needs ReactFlow context) ────────────────────────────────

interface InnerCanvasProps {
  topics: TopicSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onAddRoot: () => void;
}

function InnerCanvas({ topics, selectedId, onSelect, onAddChild, onAddRoot }: InnerCanvasProps) {
  const { fitView } = useReactFlow();

  const buildGraph = useCallback(() => {
    const rawNodes: Node[] = topics.map((t) => ({
      id: t.id,
      type: 'topicNode',
      position: { x: 0, y: 0 },
      data: { topic: t, isSelected: t.id === selectedId, onSelect, onAddChild },
    }));

    const rawEdges: Edge[] = topics
      .filter((t) => t.parentId)
      .map((t) => ({
        id: `${t.parentId}-${t.id}`,
        source: t.parentId!,
        target: t.id,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#d1d5db' },
        style: { stroke: '#d1d5db', strokeWidth: 1.5 },
      }));

    const laid = applyDagreLayout(rawNodes, rawEdges);
    return { nodes: laid, edges: rawEdges };
  }, [topics, selectedId, onSelect, onAddChild]);

  const { nodes: builtNodes, edges: builtEdges } = useMemo(() => buildGraph(), [buildGraph]);

  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(builtEdges);

  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = buildGraph();
    setNodes(newNodes);
    setEdges(newEdges);
  }, [buildGraph, setNodes, setEdges]);

  useEffect(() => {
    fitView({ padding: 0.2, duration: 300 });
  }, [topics.length, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.3}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#e5e7eb" gap={20} />
      <Controls showInteractive={false} />

      {/* Add root button */}
      <div className="absolute top-4 left-4 z-10">
        <button
          onClick={onAddRoot}
          className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Root Topic
        </button>
      </div>
    </ReactFlow>
  );
}

// ─── Public component ──────────────────────────────────────────────────────

interface TopicFlowCanvasProps {
  initialTopics: TopicSummary[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function TopicFlowCanvas({ initialTopics, selectedId, onSelect }: TopicFlowCanvasProps) {
  const [topics, setTopics] = useState<TopicSummary[]>(initialTopics);

  const handleAddRoot = async () => {
    const res = await fetch('/api/topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'New Topic' }),
    });
    if (res.ok) {
      const topic = await res.json();
      const newTopic: TopicSummary = {
        ...topic,
        _count: { videos: 0, criteria: 0, criterionFilters: 0, keywords: 0, creators: 0 },
      };
      setTopics((prev) => [...prev, newTopic]);
      onSelect(topic.id);
    }
  };

  const handleAddChild = async (parentId: string) => {
    const parent = topics.find((t) => t.id === parentId);
    const res = await fetch('/api/topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: `${parent?.name ?? 'Topic'} — sub`, parentId }),
    });
    if (res.ok) {
      const topic = await res.json();
      const newTopic: TopicSummary = {
        ...topic,
        _count: { videos: 0, criteria: 0, criterionFilters: 0, keywords: 0, creators: 0 },
      };
      setTopics((prev) => [...prev, newTopic]);
      onSelect(topic.id);
    }
  };

  // Expose a way for the detail panel to update a topic in local state
  useEffect(() => {
    const handler = (e: Event) => {
      const { topic } = (e as CustomEvent<{ topic: Partial<TopicSummary> & { id: string } }>).detail;
      setTopics((prev) => prev.map((t) => (t.id === topic.id ? { ...t, ...topic } : t)));
    };
    window.addEventListener('topic-updated', handler);
    return () => window.removeEventListener('topic-updated', handler);
  }, []);

  const handleDeleteTopic = useCallback((topicId: string) => {
    setTopics((prev) => {
      // Also remove all descendants
      const toRemove = new Set<string>();
      const queue = [topicId];
      while (queue.length) {
        const id = queue.shift()!;
        toRemove.add(id);
        prev.filter((t) => t.parentId === id).forEach((t) => queue.push(t.id));
      }
      return prev.filter((t) => !toRemove.has(t.id));
    });
    onSelect(null);
  }, [onSelect]);

  useEffect(() => {
    const handler = (e: Event) => {
      const { topicId } = (e as CustomEvent<{ topicId: string }>).detail;
      handleDeleteTopic(topicId);
    };
    window.addEventListener('topic-deleted', handler);
    return () => window.removeEventListener('topic-deleted', handler);
  }, [handleDeleteTopic]);

  return (
    <ReactFlowProvider>
      <InnerCanvas
        topics={topics}
        selectedId={selectedId}
        onSelect={(id) => onSelect(id === selectedId ? null : id)}
        onAddChild={handleAddChild}
        onAddRoot={handleAddRoot}
      />
    </ReactFlowProvider>
  );
}
