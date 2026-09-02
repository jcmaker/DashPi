import { build } from 'esbuild';
import { cp, mkdir, rm } from 'node:fs/promises';

await rm('dist', { recursive: true, force: true });
await cp('public', 'dist', { recursive: true });
await build({
  entryPoints: { sender: 'src/sender.ts' },
  bundle: true,
  format: 'esm',
  target: ['safari17', 'chrome120'],
  outdir: 'dist/assets',
  minify: true,
});
await mkdir('../src/dashpi/web/assets', { recursive: true });
await cp('dist/assets/sender.js', '../src/dashpi/web/assets/sender.js');
await cp('dist/sender.html', '../src/dashpi/web/sender.html');
