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

test('drops an over-limit frame before it can store blocks', () => {
  const collector = new FrameCollector();
  const over: OpticalFrame = {
    sessionId: 9,
    sequence: 0,
    blockCount: 16385,
    blockSize: 1024,
    totalLength: 16 * 1024 * 1024 + 1,
    indices: [0],
    symbol: new Uint8Array(1024),
  };

  assert.throws(() => collector.add(over), /malformed stream/);
  assert.equal(collector.identity, '');
  assert.deepEqual(collector.progress, { recovered: 0, total: 0 });

  collector.add(frame(1, 0, [97, 98]));
  assert.throws(() => collector.add(over), /malformed stream/);
  assert.deepEqual(collector.progress, { recovered: 1, total: 2 });
  assert.ok(collector.identity.startsWith('1:'));
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
