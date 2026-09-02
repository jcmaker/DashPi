import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import fixture from '../../tests/fixtures/optical-e2e.json' with { type: 'json' };
import { unpackContainer } from '../src/optical/container.ts';
import { FountainDecoder } from '../src/optical/fountain.ts';
import { parseFrame } from '../src/optical/protocol.ts';

function fromHex(hex: string): Uint8Array {
  return Uint8Array.from(Buffer.from(hex, 'hex'));
}

test('browser recovers the Python one-megabyte loss fixture', async () => {
  const first = parseFrame(fromHex(fixture.frames_hex[0]));
  const decoder = new FountainDecoder(first.blockCount, first.blockSize, first.totalLength);

  for (const hex of fixture.frames_hex) {
    decoder.add(parseFrame(fromHex(hex)));
    if (decoder.result()) break;
  }

  const packed = decoder.result();
  assert.ok(packed);
  const file = await unpackContainer(packed);
  assert.equal(file.payload.length, 1024 * 1024);
  assert.equal(createHash('sha256').update(file.payload).digest('hex'), fixture.payload_sha256);
});
