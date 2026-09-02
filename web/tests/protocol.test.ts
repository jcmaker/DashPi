import assert from 'node:assert/strict';
import test from 'node:test';
import vector from '../../tests/fixtures/optical-v1.json' with { type: 'json' };
import { parseFrame } from '../src/optical/protocol.ts';

function wireBytes(): Uint8Array {
  return Uint8Array.from(
    vector.wire_hex.match(/../g)!.map((value) => Number.parseInt(value, 16)),
  );
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function updateCrc(bytes: Uint8Array): void {
  new DataView(bytes.buffer).setUint32(bytes.length - 4, crc32(bytes.subarray(0, -4)), true);
}

test('parses the Python golden vector', () => {
  const frame = parseFrame(wireBytes());

  assert.deepEqual(frame, {
    sessionId: 0x01020304,
    sequence: 5,
    blockCount: 3,
    blockSize: 4,
    totalLength: 10,
    indices: [0, 2],
    symbol: Uint8Array.of(97, 98, 99, 100),
  });
});

test('rejects a golden frame with a corrupted CRC', () => {
  const bytes = wireBytes();
  bytes[bytes.length - 1] ^= 1;

  assert.throws(() => parseFrame(bytes), /crc mismatch/);
});

test('rejects a checksummed frame whose total length exceeds its geometry', () => {
  const bytes = wireBytes();
  new DataView(bytes.buffer).setUint32(18, 13, true);
  updateCrc(bytes);

  assert.throws(() => parseFrame(bytes), /malformed frame/);
});

test('rejects checksummed frames outside the v1 header boundary', () => {
  const cases: [string, (bytes: Uint8Array) => void, RegExp][] = [
    ['an unsupported version', (bytes) => { bytes[4] = 2; }, /unsupported protocol/],
    ['nonzero flags', (bytes) => { bytes[5] = 1; }, /unsupported protocol/],
    ['duplicate block indices', (bytes) => { bytes[25] = 0; }, /malformed frame/],
    ['an out-of-range block index', (bytes) => { bytes[25] = 3; }, /malformed frame/],
  ];

  for (const [description, mutate, expected] of cases) {
    const bytes = wireBytes();
    mutate(bytes);
    updateCrc(bytes);
    assert.throws(() => parseFrame(bytes), expected, description);
  }
});
