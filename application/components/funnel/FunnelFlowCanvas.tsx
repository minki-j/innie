'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
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

export interface FunnelSummary {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  _count: {
    funnelVideos: number;
    classNodes: number;
    keywords: number;
    creators: number;
  };
}

export interface ClassNodeFlat {
  id: string;
  title: string;
  description: string | null;
  parentClassNodeId: string | null;
  funnelId: string | null;
}

export interface SelectedClassNode {
  id: string;
  funnelId: string;
  title: string;
  description: string | null;
}

type Direction = 'LR' | 'TB';

interface PendingDelete {
  type: 'funnel' | 'classNode';
  id: string;
  funnelId?: string;
  label: string;
}

interface FunnelNodeData {
  funnel: FunnelSummary;
  isSelected: boolean;
  direction: Direction;
  onAddRootClassNode: (funnelId: string) => void;
  onRequestDelete: (p: PendingDelete) => void;
}

interface ClassNodeData {
  classNode: ClassNodeFlat;
  direction: Direction;
  isSelected: boolean;
  onAddChild: (parentId: string, funnelId: string) => void;
  onRequestDelete: (p: PendingDelete) => void;
}

const FUNNEL_NODE_WIDTH = 220;
const FUNNEL_NODE_HEIGHT = 100;
const CLASS_NODE_WIDTH = 200;
const CLASS_NODE_HEIGHT = 60;

function applyDagreLayout(nodes: Node[], edges: Edge[], direction: Direction): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, nodesep: 40, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => {
    const isClass = n.type === 'classNode';
    g.setNode(n.id, {
      width: isClass ? CLASS_NODE_WIDTH : FUNNEL_NODE_WIDTH,
      height: isClass ? CLASS_NODE_HEIGHT : FUNNEL_NODE_HEIGHT,
    });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    const isClass = n.type === 'classNode';
    const w = isClass ? CLASS_NODE_WIDTH : FUNNEL_NODE_WIDTH;
    const h = isClass ? CLASS_NODE_HEIGHT : FUNNEL_NODE_HEIGHT;
    return { ...n, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
  });
}

const PlusIcon = () => (
  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

function FunnelNodeCard({ data }: NodeProps) {
  const { funnel, isSelected, direction, onAddRootClassNode, onRequestDelete } =
    data as unknown as FunnelNodeData;
  const targetPos = direction === 'LR' ? Position.Left : Position.Top;
  const sourcePos = direction === 'LR' ? Position.Right : Position.Bottom;

  return (
    <div
      className={`group relative w-[220px] bg-white border-2 rounded-xl shadow-sm cursor-pointer transition-all hover:shadow-md ${isSelected
          ? 'border-blue-500 shadow-blue-100 shadow-md'
          : 'border-gray-200 hover:border-gray-300'
        }`}
    >
      <Handle type="target" position={targetPos} className="!invisible" />

      <button
        onClick={(e) => {
          e.stopPropagation();
          onRequestDelete({ type: 'funnel', id: funnel.id, label: funnel.name });
        }}
        title="Delete topic"
        className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all hover:bg-red-500 hover:text-white cursor-pointer z-10"
        >
          <TrashIcon />
        </button>

      <div className="p-3">
        <div className="flex items-center gap-2 mb-1">
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${funnel.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}
          >
            {funnel.active ? 'Active' : 'Paused'}
          </span>
        </div>
        <p className="font-semibold text-gray-900 text-sm leading-tight line-clamp-2">
          {funnel.name}
        </p>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-400">
          <span>{funnel._count.funnelVideos} videos</span>
        </div>
      </div>

      <button
        onClick={(e) => { e.stopPropagation(); onAddRootClassNode(funnel.id); }}
        title="Add class node"
        className="absolute bottom-2 right-2 w-5 h-5 rounded-full bg-gray-100 hover:bg-blue-100 hover:text-blue-600 text-gray-400 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
      >
        <PlusIcon />
      </button>

      <Handle type="source" position={sourcePos} className="!invisible" />
    </div>
  );
}

function ClassNodeCard({ data }: NodeProps) {
  const { classNode, direction, isSelected, onAddChild, onRequestDelete } =
    data as unknown as ClassNodeData;
  const targetPos = direction === 'LR' ? Position.Left : Position.Top;
  const sourcePos = direction === 'LR' ? Position.Right : Position.Bottom;
  const isPending = classNode.id.startsWith('temp-');

  return (
    <div
      className={`group relative w-[200px] bg-white border rounded-lg shadow-sm p-2.5 transition-all ${isPending
          ? 'opacity-60 cursor-default border-gray-200'
          : isSelected
            ? 'border-blue-400 ring-1 ring-blue-300 cursor-pointer hover:shadow-md'
            : 'border-gray-200 hover:border-gray-300 cursor-pointer hover:shadow-md'
        }`}
    >
      <Handle type="target" position={targetPos} className="!invisible" />

      {isPending ? (
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin shrink-0" />
          <p className="text-xs text-gray-400 leading-snug">Creating…</p>
        </div>
      ) : (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
          onRequestDelete({
            type: 'classNode',
            id: classNode.id,
            funnelId: classNode.funnelId ?? '',
            label: classNode.title || 'Untitled',
          });
            }}
            title="Delete class node"
            className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all hover:bg-red-500 hover:text-white cursor-pointer z-10"
          >
            <TrashIcon />
          </button>

          <p className="text-xs font-medium text-gray-900 leading-snug line-clamp-2 pr-1">{classNode.title || 'Untitled'}</p>
          {classNode.description && (
            <p className="text-[11px] text-gray-400 leading-snug line-clamp-1 mt-0.5 pr-1">{classNode.description}</p>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation();
              onAddChild(classNode.id, classNode.funnelId ?? '');
            }}
            title="Add child class node"
            className="absolute bottom-1.5 right-1.5 w-5 h-5 rounded-full bg-gray-100 hover:bg-blue-100 hover:text-blue-600 text-gray-400 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
          >
            <PlusIcon />
          </button>
        </>
      )}

      <Handle type="source" position={sourcePos} className="!invisible" />
    </div>
  );
}

const nodeTypes = { funnelNode: FunnelNodeCard, classNode: ClassNodeCard };

interface InnerCanvasProps {
  funnels: FunnelSummary[];
  classNodesByFunnel: Record<string, ClassNodeFlat[]>;
  selectedFunnelId: string | null;
  selectedClassNodeId: string | null;
  direction: Direction;
  onSelectFunnel: (id: string | null) => void;
  onSelectClassNode: (cn: SelectedClassNode | null) => void;
  onAddFunnel: () => void;
  onAddRootClassNode: (funnelId: string) => void;
  onAddChildClassNode: (parentId: string, funnelId: string) => void;
  onToggleDirection: () => void;
  onDeleteFunnel: (funnelId: string) => Promise<void>;
  onDeleteClassNode: (classNodeId: string, funnelId: string) => Promise<void>;
}

function InnerCanvas({
  funnels,
  classNodesByFunnel,
  selectedFunnelId,
  selectedClassNodeId,
  direction,
  onSelectFunnel,
  onSelectClassNode,
  onAddFunnel,
  onAddRootClassNode,
  onAddChildClassNode,
  onToggleDirection,
  onDeleteFunnel,
  onDeleteClassNode,
}: InnerCanvasProps) {
  const { fitView } = useReactFlow();

  const selectNode = useCallback(
    (node: Node) => {
      if (node.type === 'funnelNode') {
        const funnel = (node.data as unknown as FunnelNodeData).funnel;
        onSelectFunnel(funnel.id === selectedFunnelId ? null : funnel.id);
      } else if (node.type === 'classNode') {
        const cn = (node.data as unknown as ClassNodeData).classNode;
        if (cn.id.startsWith('temp-')) return;
        onSelectClassNode(
          cn.id === selectedClassNodeId
            ? null
            : { id: cn.id, funnelId: cn.funnelId ?? '', title: cn.title, description: cn.description },
        );
      }
    },
    [selectedFunnelId, selectedClassNodeId, onSelectFunnel, onSelectClassNode],
  );

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => selectNode(node),
    [selectNode],
  );

  const handleNodeDragStart = useCallback(
    (_event: React.MouseEvent, node: Node) => selectNode(node),
    [selectNode],
  );
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    try {
      if (pendingDelete.type === 'funnel') {
        await onDeleteFunnel(pendingDelete.id);
      } else {
        await onDeleteClassNode(pendingDelete.id, pendingDelete.funnelId!);
      }
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }, [pendingDelete, deleting, onDeleteFunnel, onDeleteClassNode]);

  const handleRequestDelete = useCallback((p: PendingDelete) => {
    setPendingDelete(p);
  }, []);

  const totalClassNodes = Object.values(classNodesByFunnel).reduce(
    (sum, nodes) => sum + nodes.length,
    0,
  );

  const buildGraph = useCallback(() => {
    const rawNodes: Node[] = funnels.map((f) => ({
      id: f.id,
      type: 'funnelNode',
      position: { x: 0, y: 0 },
      data: {
        funnel: f,
        isSelected: f.id === selectedFunnelId,
        direction,
        onAddRootClassNode,
        onRequestDelete: handleRequestDelete,
      },
    }));

    const rawEdges: Edge[] = [];

    for (const funnel of funnels) {
      const classNodes = classNodesByFunnel[funnel.id] ?? [];
      for (const cn of classNodes) {
        rawNodes.push({
          id: `cn-${cn.id}`,
          type: 'classNode',
          position: { x: 0, y: 0 },
          data: {
            classNode: cn,
            direction,
            isSelected: cn.id === selectedClassNodeId,
            onAddChild: onAddChildClassNode,
            onRequestDelete: handleRequestDelete,
          },
        });

        const sourceId = cn.parentClassNodeId
          ? `cn-${cn.parentClassNodeId}`
          : funnel.id;
        rawEdges.push({
          id: `e-${sourceId}-cn-${cn.id}`,
          source: sourceId,
          target: `cn-${cn.id}`,
          markerEnd: { type: MarkerType.ArrowClosed, color: '#d1d5db' },
          style: { stroke: '#d1d5db' },
        });
      }
    }

    const laid = applyDagreLayout(rawNodes, rawEdges, direction);
    return { nodes: laid, edges: rawEdges };
  }, [
    funnels,
    classNodesByFunnel,
    selectedFunnelId,
    selectedClassNodeId,
    direction,
    onAddRootClassNode,
    onAddChildClassNode,
    handleRequestDelete,
  ]);

  const { nodes: builtNodes, edges: builtEdges } = useMemo(
    () => buildGraph(),
    [buildGraph],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(builtEdges);

  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = buildGraph();
    setNodes(newNodes);
    setEdges(newEdges);
  }, [buildGraph, setNodes, setEdges]);

  useEffect(() => {
    fitView({ padding: 0.2, duration: 300 });
  }, [funnels.length, totalClassNodes, direction, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      onNodeClick={handleNodeClick}
      onNodeDragStart={handleNodeDragStart}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.3}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#e5e7eb" gap={20} />

      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={onAddFunnel}
            className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 shadow-sm transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Topic
          </button>

          <button
            onClick={() => fitView({ padding: 0.05, duration: 300 })}
            title="Fit nodes to screen"
            className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 shadow-sm transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
            Arrange
          </button>

          <button
            onClick={onToggleDirection}
            title={direction === 'LR' ? 'Switch to vertical layout' : 'Switch to horizontal layout'}
            className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 shadow-sm transition-colors cursor-pointer"
          >
            {direction === 'LR' ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12h18M3 6h18M3 18h18" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v18M6 3v18M18 3v18" />
              </svg>
            )}
            {direction === 'LR' ? 'Vertical' : 'Horizontal'}
          </button>
        </div>
      </div>

      {pendingDelete && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center bg-black/25"
          onKeyDown={(e) => { if (e.key === 'Escape') setPendingDelete(null); }}
        >
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-80 mx-4">
            <div className="flex items-start gap-3 mb-4">
              <div className="shrink-0 w-9 h-9 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-4 h-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  Delete {pendingDelete.type === 'funnel' ? 'topic' : 'class node'}?
                </p>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                  &ldquo;{pendingDelete.label}&rdquo;
                </p>
                {pendingDelete.type === 'funnel' && (
                  <p className="text-xs text-red-500 mt-1.5">
                    All class nodes and pipeline data will be permanently removed.
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setPendingDelete(null)}
                disabled={deleting}
                className="px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={deleting}
                className="px-3 py-1.5 text-sm font-medium text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ReactFlow>
  );
}

interface FunnelFlowCanvasProps {
  initialFunnels: FunnelSummary[];
  selectedFunnelId: string | null;
  selectedClassNodeId: string | null;
  onSelectFunnel: (id: string | null) => void;
  onSelectClassNode: (cn: SelectedClassNode | null) => void;
  onFunnelAdded?: (funnel: FunnelSummary) => void;
}

export function FunnelFlowCanvas({
  initialFunnels,
  selectedFunnelId,
  selectedClassNodeId,
  onSelectFunnel,
  onSelectClassNode,
  onFunnelAdded,
}: FunnelFlowCanvasProps) {
  const [funnels, setFunnels] = useState<FunnelSummary[]>(initialFunnels);
  const [classNodesByFunnel, setClassNodesByFunnel] = useState<
    Record<string, ClassNodeFlat[]>
  >({});
  const [direction, setDirection] = useState<Direction>('LR');

  // Fetch class nodes for all funnels on mount
  useEffect(() => {
    if (initialFunnels.length === 0) return;
    Promise.all(
      initialFunnels.map(async (f) => {
        const r = await fetch(`/api/funnels/${f.id}/class-nodes`);
        const data: ClassNodeFlat[] = r.ok ? await r.json() : [];
        return [f.id, data] as const;
      }),
    ).then((entries) => setClassNodesByFunnel(Object.fromEntries(entries)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggleDirection = useCallback(() => {
    setDirection((d) => (d === 'LR' ? 'TB' : 'LR'));
  }, []);

  const handleAddFunnel = async () => {
    const res = await fetch('/api/funnels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'New Topic' }),
    });
    if (res.ok) {
      const funnel = await res.json();
      const newFunnel: FunnelSummary = {
        ...funnel,
        _count: { funnelVideos: 0, classNodes: 0, keywords: 0, creators: 0 },
      };
      setFunnels((prev) => [...prev, newFunnel]);
      setClassNodesByFunnel((prev) => ({ ...prev, [funnel.id]: [] }));
      onFunnelAdded?.(newFunnel);
      onSelectFunnel(funnel.id);
    }
  };

  const handleAddRootClassNode = useCallback(
    async (funnelId: string) => {
      const tempId = `temp-${Date.now()}`;
      const tempNode: ClassNodeFlat = { id: tempId, title: 'New class node', description: null, parentClassNodeId: null, funnelId };

      setClassNodesByFunnel((prev) => ({ ...prev, [funnelId]: [...(prev[funnelId] ?? []), tempNode] }));
      setFunnels((prev) =>
        prev.map((f) => f.id === funnelId ? { ...f, _count: { ...f._count, classNodes: f._count.classNodes + 1 } } : f),
      );

      const res = await fetch(`/api/funnels/${funnelId}/class-nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New class node' }),
      });
      if (res.ok) {
        const newNode: ClassNodeFlat = await res.json();
        setClassNodesByFunnel((prev) => ({
          ...prev,
          [funnelId]: (prev[funnelId] ?? []).map((n) => n.id === tempId ? newNode : n),
        }));
        onSelectClassNode({ id: newNode.id, funnelId, title: newNode.title, description: newNode.description });
      } else {
        setClassNodesByFunnel((prev) => ({
          ...prev,
          [funnelId]: (prev[funnelId] ?? []).filter((n) => n.id !== tempId),
        }));
        setFunnels((prev) =>
          prev.map((f) => f.id === funnelId ? { ...f, _count: { ...f._count, classNodes: f._count.classNodes - 1 } } : f),
        );
      }
    },
    [onSelectClassNode],
  );

  const handleAddChildClassNode = useCallback(
    async (parentId: string, funnelId: string) => {
      const tempId = `temp-${Date.now()}`;
      const tempNode: ClassNodeFlat = { id: tempId, title: 'New class node', description: null, parentClassNodeId: parentId, funnelId };

      setClassNodesByFunnel((prev) => ({ ...prev, [funnelId]: [...(prev[funnelId] ?? []), tempNode] }));
      setFunnels((prev) =>
        prev.map((f) => f.id === funnelId ? { ...f, _count: { ...f._count, classNodes: f._count.classNodes + 1 } } : f),
      );

      const res = await fetch(`/api/funnels/${funnelId}/class-nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New class node', parentClassNodeId: parentId }),
      });
      if (res.ok) {
        const newNode: ClassNodeFlat = await res.json();
        setClassNodesByFunnel((prev) => ({
          ...prev,
          [funnelId]: (prev[funnelId] ?? []).map((n) => n.id === tempId ? newNode : n),
        }));
        onSelectClassNode({ id: newNode.id, funnelId, title: newNode.title, description: newNode.description });
      } else {
        setClassNodesByFunnel((prev) => ({
          ...prev,
          [funnelId]: (prev[funnelId] ?? []).filter((n) => n.id !== tempId),
        }));
        setFunnels((prev) =>
          prev.map((f) => f.id === funnelId ? { ...f, _count: { ...f._count, classNodes: f._count.classNodes - 1 } } : f),
        );
      }
    },
    [onSelectClassNode],
  );

  // Sync funnel updates from FunnelDetailPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const { funnel } = (e as CustomEvent<{ funnel: Partial<FunnelSummary> & { id: string } }>)
        .detail;
      setFunnels((prev) => prev.map((f) => (f.id === funnel.id ? { ...f, ...funnel } : f)));
    };
    window.addEventListener('funnel-updated', handler);
    return () => window.removeEventListener('funnel-updated', handler);
  }, []);

  const handleDeleteFunnel = useCallback(
    (funnelId: string) => {
      setFunnels((prev) => prev.filter((f) => f.id !== funnelId));
      setClassNodesByFunnel((prev) => {
        const next = { ...prev };
        delete next[funnelId];
        return next;
      });
      onSelectFunnel(null);
    },
    [onSelectFunnel],
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const { funnelId } = (e as CustomEvent<{ funnelId: string }>).detail;
      handleDeleteFunnel(funnelId);
    };
    window.addEventListener('funnel-deleted', handler);
    return () => window.removeEventListener('funnel-deleted', handler);
  }, [handleDeleteFunnel]);

  // Sync class node deletions from ClassNodeDetailPanel or canvas delete button
  useEffect(() => {
    const handler = (e: Event) => {
      const { funnelId, deletedIds } = (
        e as CustomEvent<{ funnelId: string; deletedIds: string[] }>
      ).detail;
      const deletedSet = new Set(deletedIds);
      setClassNodesByFunnel((prev) => ({
        ...prev,
        [funnelId]: (prev[funnelId] ?? []).filter((cn) => !deletedSet.has(cn.id)),
      }));
      setFunnels((prev) =>
        prev.map((f) =>
          f.id === funnelId
            ? { ...f, _count: { ...f._count, classNodes: Math.max(0, f._count.classNodes - deletedIds.length) } }
            : f,
        ),
      );
    };
    window.addEventListener('class-node-deleted', handler);
    return () => window.removeEventListener('class-node-deleted', handler);
  }, []);

  // Sync class node updates from ClassNodeDetailPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const { classNodeId, funnelId, title, description } = (
        e as CustomEvent<{ classNodeId: string; funnelId: string; title?: string; description?: string | null }>
      ).detail;
      setClassNodesByFunnel((prev) => ({
        ...prev,
        [funnelId]: (prev[funnelId] ?? []).map((cn) =>
          cn.id === classNodeId
            ? {
                ...cn,
                ...(title !== undefined && { title }),
                ...(description !== undefined && { description }),
              }
            : cn,
        ),
      }));
    };
    window.addEventListener('class-node-updated', handler);
    return () => window.removeEventListener('class-node-updated', handler);
  }, []);

  const handleDeleteFunnelFromCanvas = useCallback(async (funnelId: string) => {
    const res = await fetch(`/api/funnels/${funnelId}`, { method: 'DELETE' });
    if (res.ok) {
      window.dispatchEvent(new CustomEvent('funnel-deleted', { detail: { funnelId } }));
      onSelectFunnel(null);
    }
  }, [onSelectFunnel]);

  const handleDeleteClassNodeFromCanvas = useCallback(
    async (classNodeId: string, funnelId: string) => {
      const res = await fetch(`/api/class-nodes/${classNodeId}`, { method: 'DELETE' });
      if (res.ok) {
        const data = await res.json();
        const deletedIds: string[] = data.deletedIds ?? [classNodeId];
        window.dispatchEvent(
          new CustomEvent('class-node-deleted', { detail: { funnelId, deletedIds } }),
        );
      }
    },
    [],
  );

  return (
    <ReactFlowProvider>
      <InnerCanvas
        funnels={funnels}
        classNodesByFunnel={classNodesByFunnel}
        selectedFunnelId={selectedFunnelId}
        selectedClassNodeId={selectedClassNodeId}
        direction={direction}
        onSelectFunnel={onSelectFunnel}
        onSelectClassNode={onSelectClassNode}
        onAddFunnel={handleAddFunnel}
        onAddRootClassNode={handleAddRootClassNode}
        onAddChildClassNode={handleAddChildClassNode}
        onToggleDirection={handleToggleDirection}
        onDeleteFunnel={handleDeleteFunnelFromCanvas}
        onDeleteClassNode={handleDeleteClassNodeFromCanvas}
      />
    </ReactFlowProvider>
  );
}
