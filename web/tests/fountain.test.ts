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

test('accepts a packed 16MiB container and rejects anything longer before storing blocks', () => {
  const maxPackedContainer = 16 * 1024 * 1024 + 49 + 255 + 255;
  const decoder = new FountainDecoder(16385, 1024, maxPackedContainer);
  assert.equal(decoder.recoveredBlocks, 0);

  assert.throws(() => new FountainDecoder(16385, 1024, maxPackedContainer + 1), /malformed stream/);
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

test('a plain block still lands after the unresolved-equation cap is full', () => {
  // A receiver that joins late first sees many repair symbols it cannot use yet.
  const blockCount = 2000;
  const decoder = new FountainDecoder(blockCount, 1, blockCount);
  const frame = (sequence: number, indices: number[]) => ({
    sessionId: 1,
    sequence,
    blockCount,
    blockSize: 1,
    totalLength: blockCount,
    indices,
    symbol: Uint8Array.of(0),
  });
  for (let sequence = 0; sequence < 1100; sequence += 1) {
    decoder.add(frame(sequence, [sequence, sequence + 1, sequence + 2]));
  }
  decoder.add(frame(5000, [1500]));
  assert.equal(decoder.recoveredBlocks, 1);
});
