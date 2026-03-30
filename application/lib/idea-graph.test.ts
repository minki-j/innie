import assert from 'node:assert/strict';
import test from 'node:test';

import {
  serializeIdeaGraph,
  serializeIdeaGraphVersion,
  type IdeaGraphVersionRecord,
  type IdeaGraphWithRelations,
} from './idea-graph';

function makeGraphVersion(overrides: Partial<IdeaGraphVersionRecord> = {}): IdeaGraphVersionRecord {
  return {
    id: overrides.id ?? 'graph_123',
    generationStatus: overrides.generationStatus ?? 'COMPLETED',
    generationError: overrides.generationError ?? null,
    generatedAt: overrides.generatedAt === undefined ? new Date('2026-03-29T16:05:00.000Z') : overrides.generatedAt,
    createdAt: overrides.createdAt ?? new Date('2026-03-29T16:00:00.000Z'),
    updatedAt: overrides.updatedAt ?? new Date('2026-03-29T16:06:00.000Z'),
  };
}

function makeGraph(overrides: Partial<IdeaGraphWithRelations> = {}): IdeaGraphWithRelations {
  return {
    id: overrides.id ?? 'graph_123',
    userId: overrides.userId ?? 'user_123',
    videoId: overrides.videoId ?? 'video_123',
    generationStatus: overrides.generationStatus ?? 'COMPLETED',
    generationError: overrides.generationError ?? null,
    generatedAt: overrides.generatedAt ?? new Date('2026-03-29T16:05:00.000Z'),
    layoutDirection: overrides.layoutDirection ?? 'LR',
    visibleDepth: overrides.visibleDepth ?? 2,
    createdAt: overrides.createdAt ?? new Date('2026-03-29T16:00:00.000Z'),
    updatedAt: overrides.updatedAt ?? new Date('2026-03-29T16:06:00.000Z'),
    nodes: overrides.nodes ?? [
      {
        id: 'node_123',
        graphId: 'graph_123',
        type: 'CLAIM',
        title: 'Main claim',
        content: 'Test content',
        x: 10,
        y: 20,
        collapsed: false,
        createdAt: new Date('2026-03-29T16:00:00.000Z'),
        updatedAt: new Date('2026-03-29T16:06:00.000Z'),
        transcriptSources: [
          {
            id: 'source_123',
            nodeId: 'node_123',
            paraphrase: 'Summary',
            quote: 'Quoted text',
            startSec: 12,
            endSec: 18,
            createdAt: new Date('2026-03-29T16:00:00.000Z'),
            updatedAt: new Date('2026-03-29T16:06:00.000Z'),
          },
        ],
      },
    ],
    edges: overrides.edges ?? [
      {
        id: 'edge_123',
        graphId: 'graph_123',
        sourceNodeId: 'node_123',
        targetNodeId: 'node_123',
        type: 'SUPPORTS',
        label: null,
        createdAt: new Date('2026-03-29T16:00:00.000Z'),
        updatedAt: new Date('2026-03-29T16:06:00.000Z'),
      },
    ],
  };
}

test('serializeIdeaGraphVersion returns version metadata for dropdown rendering', () => {
  const payload = serializeIdeaGraphVersion(
    makeGraphVersion({
      id: 'graph_version_a',
      generationStatus: 'FAILED',
      generationError: 'Agent crashed',
      generatedAt: null,
    })
  );

  assert.deepEqual(payload, {
    id: 'graph_version_a',
    generationStatus: 'FAILED',
    generationError: 'Agent crashed',
    generatedAt: null,
    createdAt: '2026-03-29T16:00:00.000Z',
    updatedAt: '2026-03-29T16:06:00.000Z',
  });
});

test('serializeIdeaGraph preserves graph identity for selected version fetches', () => {
  const payload = serializeIdeaGraph(
    makeGraph({
      id: 'graph_selected',
      createdAt: new Date('2026-03-28T08:00:00.000Z'),
      updatedAt: new Date('2026-03-28T08:10:00.000Z'),
      generatedAt: new Date('2026-03-28T08:10:00.000Z'),
    })
  );

  assert.equal(payload.id, 'graph_selected');
  assert.equal(payload.userId, 'user_123');
  assert.equal(payload.videoId, 'video_123');
  assert.equal(payload.nodes[0].id, 'node_123');
  assert.equal(payload.edges[0].id, 'edge_123');
});
