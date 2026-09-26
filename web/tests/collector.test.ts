import assert from 'node:assert/strict';
import test from 'node:test';
import { FrameCollector } from '../src/optical/collector.ts';
import type { OpticalFrame } from '../src/optical/protocol.ts';

const frame = (sessionId: number, index: number, symbol: number[]): OpticalFrame => ({
  sessionId,
  sequence: index,
  blockCount: 2,
  blockSize: 2,
  totalLength: 4,
  indices: [index],
  symbol: Uint8Array.from(symbol),
});

test('reports recovered block progress and restarts it for a new stream', () => {
  const collector = new FrameCollector();
  assert.deepEqual(collector.progress, { recovered: 0, total: 0 });

  collector.add(frame(1, 0, [97, 98]));
  assert.deepEqual(collector.progress, { recovered: 1, total: 2 });

  collector.add(frame(2, 0, [120, 121]));
  assert.deepEqual(collector.progress, { recovered: 1, total: 2 });
  assert.ok(collector.identity.startsWith('2:'));

  collector.add(frame(2, 1, [122, 33]));
  assert.deepEqual(collector.progress, { recovered: 2, total: 2 });
});
