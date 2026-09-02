import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { deflateSync } from 'node:zlib';
import { unpackContainer } from '../src/optical/container.ts';

function container(payload: Uint8Array, name = 'report.html', mediaType = 'text/html'): Uint8Array {
  const nameBytes = Buffer.from(name);
  const mediaBytes = Buffer.from(mediaType);
  const body = deflateSync(payload);
  const header = Buffer.alloc(49);
  header.write('DPC1');
  header.writeUInt8(1, 4);
  header.writeUInt16LE(nameBytes.length, 5);
  header.writeUInt16LE(mediaBytes.length, 7);
  header.writeUInt32LE(payload.length, 9);
  header.writeUInt32LE(body.length, 13);
  createHash('sha256').update(payload).digest().copy(header, 17);
  return Uint8Array.from(Buffer.concat([header, nameBytes, mediaBytes, body]));
}

test('unpacks a compressed DPC1 file after SHA-256 verification', async () => {
  const payload = Uint8Array.from(Buffer.from('offline report '.repeat(32)));

  const file = await unpackContainer(container(payload));

  assert.equal(file.name, 'report.html');
  assert.equal(file.mediaType, 'text/html');
  assert.deepEqual(file.payload, payload);
});

test('rejects a DPC1 file whose payload does not match its SHA-256', async () => {
  const packed = container(Uint8Array.from(Buffer.from('incident clip '.repeat(32))));
  packed[17] ^= 0xff;

  await assert.rejects(unpackContainer(packed), /sha256 mismatch/);
});

test('rejects container metadata that is unsafe as a download name', async () => {
  const packed = container(Uint8Array.from(Buffer.from('report '.repeat(32))), '../report.html');

  await assert.rejects(unpackContainer(packed), /invalid container metadata/);
});
