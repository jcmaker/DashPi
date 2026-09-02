import { build } from 'esbuild';
import { cp, rm } from 'node:fs/promises';

await rm('dist', { recursive: true, force: true });
await cp('public', 'dist', { recursive: true });
await build({
  entryPoints: { sender: 'src/sender.ts', receiver: 'src/receiver.ts' },
  bundle: true,
  format: 'esm',
  target: ['safari17', 'chrome120'],
  outdir: 'dist/assets',
  minify: true,
});
await cp('../src/dashpi/web/tokens.css', 'dist/tokens.css');
await cp('dist', '../src/dashpi/web', { recursive: true });
