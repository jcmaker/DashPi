import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { runInNewContext } from 'node:vm';
import test from 'node:test';

const root = new URL('../../src/dashpi/web/', import.meta.url);
const html = await readFile(new URL('index.html', root), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)![1];
const incident = (id = 'A', changes = {}) => ({
  incident_id: id, triggered_at: id, state: 'ready', failure_reason: null,
  has_clip: true, has_report: true, clip_duration: 45, optical_report_available: true,
  ...changes,
});

// Only the DOM/network/timer boundaries are doubles; execute the shipped page script.
class Element {
  hidden = false;
  disabled = false;
  textContent = '';
  value = '';
  checked = false;
  src = '';
  children: Element[] = [];
  elements: Record<string, Element> = {};
  listeners: Record<string, Function> = {};
  addEventListener(name: string, fn: Function) { this.listeners[name] = fn; }
  removeAttribute(name: string) { delete this[name]; }
  replaceChildren() { this.children = []; }
  append(child: Element) { this.children.push(child); }
  querySelector(selector: string) { return this.elements[selector]; }
  click() { this.listeners.click?.({ preventDefault() {} }); }
}

async function page(fetcher: Function) {
  const nodes = Object.fromEntries(['status', 'incidents', 'detail', 'detail-heading', 'detail-status', 'report', 'video', 'report-settings', 'sender', 'optical-unavailable'].map(id => [id, new Element()]));
  nodes['report-settings'].elements = Object.fromEntries(['incident_offset_seconds', 'traffic_lights', 'lanes', 'traffic_signs', 'button', 'fieldset'].map(name => [name, new Element()]));
  const timers: Function[] = [];
  runInNewContext(script, {
    document: { querySelector: (selector: string) => nodes[selector.replace('#', '')], createElement: () => new Element() },
    fetch: fetcher,
    FormData: class {
      constructor(private form: Element) {}
      get(name: string) { return this.form.elements[name].value; }
      has(name: string) { return this.form.elements[name].checked; }
    },
    setTimeout: (callback: Function) => timers.push(callback),
  });
  const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
  await flush();
  return {
    nodes, flush,
    select: (index: number) => nodes.incidents.children[index].children[0].click(),
    submit: async () => { nodes['report-settings'].listeners.submit({ preventDefault() {} }); await flush(); },
    tick: async () => { timers.shift()?.(); await flush(); },
  };
}

const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body });

for (const state of ['ready', 'analysis_failed']) {
  test(`regeneration polls queued and absent incidents until delayed ${state} is visible`, async () => {
    let posted = false;
    let polls = 0;
    const p = await page(async (url: string, options?: any) => {
      if (options?.method === 'POST') { posted = true; return response({ state: 'analyzing' }, 202); }
      if (url.endsWith('/status')) {
        polls++;
        return response({ state: polls < 3 ? 'analyzing' : state, failure_reason: state === 'analysis_failed' ? 'model failed' : null });
      }
      if (!posted) return response([incident()]);
      return response(polls < 3 ? [] : [incident('A', { state, has_report: state === 'ready', optical_report_available: state === 'ready', failure_reason: state === 'analysis_failed' ? 'model failed' : null })]);
    });
    p.select(0);
    await p.submit();
    assert.equal(p.nodes['detail-status'].textContent, 'analyzing');
    assert.equal(p.nodes.report.hidden, true);
    assert.equal(p.nodes['report-settings'].elements.button.disabled, true);
    await p.tick();
    await p.tick();
    assert.equal(polls, 3);
    assert.equal(p.nodes['detail-status'].textContent, state === 'ready' ? 'ready' : 'model failed');
    assert.equal(p.nodes.report.hidden, state !== 'ready');
    assert.equal(p.nodes.sender.hidden, state !== 'ready');
    assert.equal(p.nodes['report-settings'].elements.button.disabled, false);
  });
}

test('switching incidents clears the manual offset before regeneration', async () => {
  const bodies: any[] = [];
  const p = await page(async (_url: string, options?: any) => {
    if (options?.method === 'POST') { bodies.push(JSON.parse(options.body)); return response({ state: 'ready' }); }
    return response([incident(), incident('B')]);
  });
  p.select(0);
  p.nodes['report-settings'].elements.incident_offset_seconds.value = '7';
  p.select(1);
  await p.submit();
  assert.equal(p.nodes['report-settings'].elements.incident_offset_seconds.value, '');
  assert.equal('incident_offset_seconds' in bodies[0], false);
});

test('unavailable reports only show the size explanation for completed reports', async () => {
  const p = await page(async () => response([
    incident('failed', { state: 'analysis_failed', has_report: false, optical_report_available: false }),
    incident('large', { optical_report_available: false }),
  ]));
  p.select(0);
  assert.equal(p.nodes['optical-unavailable'].hidden, true);
  p.select(1);
  assert.equal(p.nodes['optical-unavailable'].hidden, false);
});

test('a pending rebuild does not take selection back from another incident', async () => {
  let polls = 0;
  const p = await page(async (url: string, options?: any) => {
    if (options?.method === 'POST') return response({ state: 'analyzing' }, 202);
    if (url.endsWith('/status')) return response({ state: ++polls < 2 ? 'analyzing' : 'ready' });
    return response([incident(), incident('B')]);
  });
  p.select(0);
  await p.submit();
  p.select(1);
  await p.tick();
  assert.equal(polls, 2);
  assert.equal(p.nodes['detail-heading'].textContent, 'B');
});

test('hidden detail, report controls and sender link have no rendered boxes', { skip: !process.env.DASHPI_BROWSER }, async () => {
  const directory = await mkdtemp(join(tmpdir(), 'dashpi-visibility-'));
  try {
    const css = await readFile(new URL('tokens.css', root), 'utf8');
    const document = html.replace('<link rel="stylesheet" href="/tokens.css">', `<style>${css}</style>`)
      .replace(/<script>[\s\S]*?<\/script>/, `<script>
        const targets = ['detail', 'report-settings', 'sender'].map(id => document.getElementById(id));
        document.getElementById('detail').hidden = false;
        const childrenHidden = targets.slice(1).every(el => getComputedStyle(el).display === 'none' && el.getClientRects().length === 0);
        targets[0].hidden = true;
        const detailHidden = getComputedStyle(targets[0]).display === 'none' && targets[0].getClientRects().length === 0;
        document.body.textContent = childrenHidden && detailHidden ? 'VISIBILITY_PASS' : 'VISIBILITY_FAIL';
      </script>`);
    const path = join(directory, 'test.html');
    await writeFile(path, document);
    const output = execFileSync(process.env.DASHPI_BROWSER!, ['--headless', '--disable-gpu', '--no-first-run', `--user-data-dir=${directory}/profile`, '--dump-dom', `file://${path}`], { encoding: 'utf8', timeout: 15000 });
    assert.match(output, /VISIBILITY_PASS/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
