import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import type { OpticalFrame } from '../src/optical/protocol.ts';
import { FrameCollector, messageForFrameError } from '../src/receiver.ts';

test('receiver keeps camera start and verified save explicit', async () => {
  const html = await readFile(new URL('../public/receiver.html', import.meta.url), 'utf8');

  assert.equal(/https?:\/\//.test(html), false);
  assert.ok(html.includes('Start camera'));
  assert.ok(html.includes('Stop camera'));
  assert.ok(html.includes('Save verified file'));
  assert.ok(html.includes('id="save" hidden'));
  assert.ok(html.includes('sandbox="allow-scripts allow-downloads allow-modals"'));
  assert.equal(html.includes('allow-same-origin'), false);
});

test('keeps foreign QR errors silent and explains unsupported DashPi versions', () => {
  assert.equal(messageForFrameError(new Error('foreign frame')), undefined);
  assert.equal(messageForFrameError(new Error('crc mismatch')), undefined);
  assert.equal(
    messageForFrameError(new Error('unsupported protocol')),
    '이 송신 형식을 읽으려면 수신기를 업데이트하세요.',
  );
});

test('resets incomplete recovery when a new optical stream arrives', () => {
  const collector = new FrameCollector();
  const frame = (sessionId: number, index: number, symbol: number[]): OpticalFrame => ({
    sessionId,
    sequence: index,
    blockCount: 2,
    blockSize: 2,
    totalLength: 4,
    indices: [index],
    symbol: Uint8Array.from(symbol),
  });

  assert.equal(collector.add(frame(1, 0, [97, 98])), undefined);
  assert.equal(collector.add(frame(2, 0, [120, 121])), undefined);
  assert.deepEqual(collector.add(frame(2, 1, [122, 33])), Uint8Array.from([120, 121, 122, 33]));
});
