// npm ci reinstalls expo-camera from the registry, which drops Android's QR
// payload on the floor (displayValue / UTF-8 String(rawBytes)). Re-apply the
// rawBytes base64 patch so the next native build still delivers frame bytes.
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const camera = join(root, 'node_modules/expo-camera')
const marker = join(camera, 'android/src/main/java/expo/modules/camera/common/CommonEvents.kt')
const patch = join(root, 'patches/expo-camera+57.0.5.patch')

if (!existsSync(camera)) process.exit(0)

const version = JSON.parse(readFileSync(join(camera, 'package.json'), 'utf8')).version
if (version !== '57.0.5') {
  console.error(`expo-camera ${version} is not 57.0.5; update patches/expo-camera+57.0.5.patch`)
  process.exit(1)
}

if (readFileSync(marker, 'utf8').includes('rawBytesBase64')) process.exit(0)

const result = spawnSync('patch', ['-p1', '--forward', '--input', patch], {
  cwd: camera,
  stdio: 'inherit',
})
if (result.status !== 0 || !readFileSync(marker, 'utf8').includes('rawBytesBase64')) {
  console.error('Failed to patch expo-camera so Android can deliver QR rawBytes')
  process.exit(result.status || 1)
}
