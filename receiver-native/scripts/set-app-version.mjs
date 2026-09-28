// Usage: node scripts/set-app-version.mjs 1.2.3
// Writes expo.version and a monotonically increasing android.versionCode into app.json.
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export function versionCode(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version)
  if (!match) throw new Error(`not a MAJOR.MINOR.PATCH version: ${version}`)
  const [major, minor, patch] = match.slice(1).map(Number)
  if (minor > 99 || patch > 99) throw new Error(`minor and patch must be 0-99: ${version}`)
  return major * 10000 + minor * 100 + patch
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const version = process.argv[2]
  const path = new URL('../app.json', import.meta.url)
  const app = JSON.parse(readFileSync(path, 'utf8'))
  app.expo.version = version
  app.expo.android = { ...app.expo.android, versionCode: versionCode(version) }
  writeFileSync(path, `${JSON.stringify(app, null, 2)}\n`)
  console.log(`app.json → ${version} (versionCode ${app.expo.android.versionCode})`)
}
