import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { resolveWhileCurrent, runFrameLoop, updateStatus } from '../src/sender.ts';

test('requires confidentiality acknowledgement and calibration controls', async () => {
  const html = await readFile(new URL('../public/sender.html', import.meta.url), 'utf8');

  for (const text of ['not encrypted', 'line of sight', 'bytes/frame', 'QR scale', 'frames/second']) {
    assert.ok(html.includes(text), `missing sender copy: ${text}`);
  }
  assert.ok(html.includes('type="checkbox"'));
  assert.ok(html.includes('안전한 장소에 정차했고'));
  assert.ok(html.indexOf('<option value="report">') < html.indexOf('<option value="clip">'));
  assert.ok(html.includes('<button id="start" type="button" disabled>'));
});

test('waits for each QR render before starting another frame', async () => {
  let calls = 0;
  let running = true;
  let release!: () => void;
  const renderGate = new Promise<void>((resolve) => { release = resolve; });

  const loop = runFrameLoop(
    async () => { calls += 1; await renderGate; },
    () => running,
    async () => {},
  );
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(calls, 1);
  running = false;
  release();
  await loop;
});

test('clears a prior error tone when status returns to normal', () => {
  const target = { textContent: '', dataset: { tone: 'error' } };

  updateStatus(target, 'ready');

  assert.equal(target.textContent, 'ready');
  assert.equal(target.dataset.tone, undefined);
});

test('discards a late resource after the sender stops', async () => {
  let current = true;
  let releaseCount = 0;
  const resource = { release: async () => { releaseCount += 1; } };
  let resolve!: (value: typeof resource) => void;
  const pending = new Promise<typeof resource>((done) => { resolve = done; });

  const result = resolveWhileCurrent(pending, () => current, (value) => value.release());
  current = false;
  resolve(resource);

  assert.equal(await result, undefined);
  assert.equal(releaseCount, 1);
});
