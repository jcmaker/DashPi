import assert from 'node:assert/strict';
import test from 'node:test';
import { FountainDecoder } from '../src/optical/fountain.ts';

test('recovers carried equations without a shared PRNG', () => {
  const decoder = new FountainDecoder(2, 3, 6);

  decoder.add({
    sessionId: 1,
    sequence: 1,
    blockCount: 2,
    blockSize: 3,
    totalLength: 6,
    indices: [1],
    symbol: Uint8Array.of(100, 101, 102),
  });
  decoder.add({
    sessionId: 1,
    sequence: 0,
    blockCount: 2,
    blockSize: 3,
    totalLength: 6,
    indices: [0],
    symbol: Uint8Array.of(97, 98, 99),
  });

  assert.deepEqual(decoder.result(), Uint8Array.of(97, 98, 99, 100, 101, 102));
});

test('rejects another session before it can corrupt the result', () => {
  const decoder = new FountainDecoder(2, 1, 2);
  const firstSession = {
    sessionId: 1,
    sequence: 0,
    blockCount: 2,
    blockSize: 1,
    totalLength: 2,
    indices: [0],
    symbol: Uint8Array.of(97),
  };

  decoder.add(firstSession);
  assert.throws(
    () => decoder.add({ ...firstSession, sessionId: 2, sequence: 0, indices: [1], symbol: Uint8Array.of(120) }),
    /stream changed/,
  );
  decoder.add({ ...firstSession, sequence: 1, indices: [1], symbol: Uint8Array.of(98) });

  assert.deepEqual(decoder.result(), Uint8Array.of(97, 98));
});

test('rejects a conflicting equation that reduces to a solved block', () => {
  const decoder = new FountainDecoder(1, 3, 3);
  const first = {
    sessionId: 1,
    sequence: 0,
    blockCount: 1,
    blockSize: 3,
    totalLength: 3,
    indices: [0],
    symbol: Uint8Array.of(97, 98, 99),
  };

  decoder.add(first);
  assert.throws(
    () => decoder.add({ ...first, sequence: 1, symbol: Uint8Array.of(100, 101, 102) }),
    /conflicting equation/,
  );
});

test('rejects contradictory unresolved equations after peeling', () => {
  const decoder = new FountainDecoder(3, 1, 3);
  const frame = (indices: number[], symbol: number) => ({
    sessionId: 1,
    sequence: 0,
    blockCount: 3,
    blockSize: 1,
    totalLength: 3,
    indices,
    symbol: Uint8Array.of(symbol),
  });

  decoder.add(frame([0, 1], 3));
  decoder.add(frame([0, 1, 2], 7));
  assert.throws(() => decoder.add(frame([2], 3)), /conflicting equation/);
});

test('rejects malformed symbols before changing decoder state', () => {
  const decoder = new FountainDecoder(2, 1, 2);
  const frame = {
    sessionId: 1,
    sequence: 0,
    blockCount: 2,
    blockSize: 1,
    totalLength: 2,
    indices: [0],
    symbol: Uint8Array.of(97),
  };

  assert.throws(
    () => decoder.add({ ...frame, symbol: Uint8Array.of(97, 98) }),
    /malformed frame/,
  );
  decoder.add(frame);
  decoder.add({ ...frame, sequence: 1, indices: [1], symbol: Uint8Array.of(98) });
  assert.deepEqual(decoder.result(), Uint8Array.of(97, 98));
});
