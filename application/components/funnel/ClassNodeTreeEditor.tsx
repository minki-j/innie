'use client';

import { useState, useEffect } from 'react';

interface GoldStandard {
  id: string;
  videoUrl: string;
  title: string | null;
  isPositive: boolean;
  note: string | null;
}

interface ClassNode {
  id: string;
  description: string;
  parentClassNodeId: string | null;
  funnelId: string | null;
  goldStandards: GoldStandard[];
  _count: { results: number; childrenClassNodes: number };
}

interface ClassNodeTreeEditorProps {
  funnelId: string;
}

type ClassNodeWithChildren = ClassNode & { children: ClassNodeWithChildren[] };

function buildTree(nodes: ClassNode[]): ClassNodeWithChildren[] {
  const nodeMap = new Map<string, ClassNodeWithChildren>();
  for (const n of nodes) {
    nodeMap.set(n.id, { ...n, children: [] });
  }
  const roots: ClassNodeWithChildren[] = [];
  for (const n of nodeMap.values()) {
    if (n.parentClassNodeId && nodeMap.has(n.parentClassNodeId)) {
      nodeMap.get(n.parentClassNodeId)!.children.push(n);
    } else {
      roots.push(n);
    }
  }
  return roots;
}

interface NodeRowProps {
  node: ClassNodeWithChildren;
  depth: number;
  funnelId: string;
  onRefresh: () => void;
}

function NodeRow({ node, depth, funnelId, onRefresh }: NodeRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);
  const [description, setDescription] = useState(node.description);
  const [isSaving, setIsSaving] = useState(false);
  const [addingGold, setAddingGold] = useState(false);
  const [newGoldUrl, setNewGoldUrl] = useState('');
  const [newGoldTitle, setNewGoldTitle] = useState('');
  const [newGoldIsPositive, setNewGoldIsPositive] = useState(true);
  const [newGoldNote, setNewGoldNote] = useState('');
  const [isAddingGold, setIsAddingGold] = useState(false);

  const handleSaveDesc = async () => {
    if (!description.trim() || isSaving) return;
    setIsSaving(true);
    try {
      const res = await fetch(`/api/class-nodes/${node.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description.trim() }),
      });
      if (res.ok) {
        setEditingDesc(false);
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to save class node:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    const msg = node._count.childrenClassNodes > 0
      ? `Delete this node and its ${node._count.childrenClassNodes} children?`
      : 'Delete this class node?';
    if (!confirm(msg)) return;
    try {
      const res = await fetch(`/api/class-nodes/${node.id}`, { method: 'DELETE' });
      if (res.ok) onRefresh();
    } catch (err) {
      console.error('Failed to delete class node:', err);
    }
  };

  const handleAddChild = async () => {
    try {
      const res = await fetch(`/api/funnels/${funnelId}/class-nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: 'New class node', parentClassNodeId: node.id }),
      });
      if (res.ok) {
        setExpanded(true);
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to add child class node:', err);
    }
  };

  const handleAddGoldStandard = async () => {
    if (!newGoldUrl.trim() || isAddingGold) return;
    setIsAddingGold(true);
    try {
      const res = await fetch(`/api/class-nodes/${node.id}/gold-standards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoUrl: newGoldUrl.trim(),
          title: newGoldTitle.trim() || null,
          isPositive: newGoldIsPositive,
          note: newGoldNote.trim() || null,
        }),
      });
      if (res.ok) {
        setAddingGold(false);
        setNewGoldUrl('');
        setNewGoldTitle('');
        setNewGoldNote('');
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to add gold standard:', err);
    } finally {
      setIsAddingGold(false);
    }
  };

  const handleDeleteGold = async (goldId: string) => {
    try {
      const res = await fetch(`/api/class-nodes/${node.id}/gold-standards?id=${goldId}`, {
        method: 'DELETE',
      });
      if (res.ok) onRefresh();
    } catch (err) {
      console.error('Failed to delete gold standard:', err);
    }
  };

  const indentPx = depth * 20;

  return (
    <div>
      <div
        className="group flex items-start gap-2 py-2 border-b border-gray-100 hover:bg-gray-50 transition-colors"
        style={{ paddingLeft: `${indentPx + 8}px` }}
      >
        {/* Expand toggle */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 mt-0.5 p-0.5 rounded text-gray-400 hover:text-gray-600"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>

        {/* Description */}
        <div className="flex-1 min-w-0">
          {editingDesc ? (
            <div className="flex items-start gap-2">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                autoFocus
                className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 resize-vertical"
              />
              <div className="flex flex-col gap-1 shrink-0">
                <button
                  onClick={handleSaveDesc}
                  disabled={isSaving}
                  className="px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  onClick={() => { setEditingDesc(false); setDescription(node.description); }}
                  className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded hover:bg-gray-200"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-800 leading-snug">{node.description}</p>
          )}
          <div className="flex items-center gap-2 mt-0.5 text-[11px] text-gray-400">
            {node._count.results > 0 && <span>{node._count.results} results</span>}
            {node.goldStandards.length > 0 && (
              <span>{node.goldStandards.length} examples</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => setExpanded(true)}
            title="Add child node"
            className="p-1 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600"
            onMouseDown={(e) => { e.preventDefault(); handleAddChild(); }}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
          <button
            onClick={() => setEditingDesc(true)}
            title="Edit"
            className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button
            onClick={handleDelete}
            title="Delete"
            className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded panel: gold standards + children */}
      {expanded && (
        <div style={{ paddingLeft: `${indentPx + 28}px` }}>
          {/* Gold standards */}
          <div className="py-2 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500">Gold Standards</span>
              <button
                onClick={() => setAddingGold(true)}
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                + Add
              </button>
            </div>

            {node.goldStandards.length > 0 && (
              <div className="space-y-1">
                {node.goldStandards.map((gs) => (
                  <div key={gs.id} className="flex items-start justify-between gap-2 py-1">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${gs.isPositive ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                          {gs.isPositive ? 'Positive' : 'Negative'}
                        </span>
                        {gs.title && <span className="text-xs text-gray-700 truncate">{gs.title}</span>}
                      </div>
                      <a href={gs.videoUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline truncate block">
                        {gs.videoUrl}
                      </a>
                    </div>
                    <button
                      onClick={() => handleDeleteGold(gs.id)}
                      className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 shrink-0"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {addingGold && (
              <div className="border border-gray-200 rounded p-2 space-y-2 bg-white">
                <input
                  type="text"
                  value={newGoldUrl}
                  onChange={(e) => setNewGoldUrl(e.target.value)}
                  placeholder="YouTube video URL"
                  autoFocus
                  className="w-full px-2 py-1 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <input
                  type="text"
                  value={newGoldTitle}
                  onChange={(e) => setNewGoldTitle(e.target.value)}
                  placeholder="Title (optional)"
                  className="w-full px-2 py-1 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setNewGoldIsPositive(true)}
                    className={`px-2 py-0.5 rounded-full text-xs font-medium ${newGoldIsPositive ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
                  >
                    Positive
                  </button>
                  <button
                    onClick={() => setNewGoldIsPositive(false)}
                    className={`px-2 py-0.5 rounded-full text-xs font-medium ${!newGoldIsPositive ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'}`}
                  >
                    Negative
                  </button>
                </div>
                <textarea
                  value={newGoldNote}
                  onChange={(e) => setNewGoldNote(e.target.value)}
                  rows={1}
                  placeholder="Note (optional)"
                  className="w-full px-2 py-1 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => { setAddingGold(false); setNewGoldUrl(''); setNewGoldTitle(''); setNewGoldNote(''); }}
                    className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleAddGoldStandard}
                    disabled={!newGoldUrl.trim() || isAddingGold}
                    className="px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    Add
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Children */}
          {node.children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              funnelId={funnelId}
              onRefresh={onRefresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function ClassNodeTreeEditor({ funnelId }: ClassNodeTreeEditorProps) {
  const [nodes, setNodes] = useState<ClassNode[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchNodes = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/class-nodes`);
      if (res.ok) {
        const data = await res.json();
        setNodes(data);
      }
    } catch (err) {
      console.error('Failed to fetch class nodes:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [funnelId]);

  const handleAddRoot = async () => {
    try {
      const res = await fetch(`/api/funnels/${funnelId}/class-nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: 'New class node' }),
      });
      if (res.ok) fetchNodes();
    } catch (err) {
      console.error('Failed to add root class node:', err);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-400 py-4">Loading...</div>;
  }

  const tree = buildTree(nodes);

  return (
    <div className="space-y-3">
      {tree.length === 0 && (
        <p className="text-sm text-gray-500">No class nodes defined yet.</p>
      )}

      {tree.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          {tree.map((node) => (
            <NodeRow
              key={node.id}
              node={node}
              depth={0}
              funnelId={funnelId}
              onRefresh={fetchNodes}
            />
          ))}
        </div>
      )}

      <button
        onClick={handleAddRoot}
        className="w-full border border-dashed border-gray-300 rounded-lg py-2.5 text-xs text-gray-500 hover:border-gray-400 hover:text-gray-600 transition-colors flex items-center justify-center gap-1.5"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add Class Node
      </button>
    </div>
  );
}
