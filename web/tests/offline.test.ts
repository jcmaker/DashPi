import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('service worker caches only the local receiver shell', async () => {
  const source = await readFile(new URL('../public/sw.js', import.meta.url), 'utf8');

  assert.ok(source.includes('dashpi-optical-v1'));
  assert.ok(source.includes('/tokens.css'));
  assert.ok(source.includes("key.startsWith('dashpi-optical-')"));
  assert.equal(source.includes('/api/'), false);
  assert.equal(/https?:\/\//.test(source), false);
});
