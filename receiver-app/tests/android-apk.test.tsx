import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { androidApkPath } from '../src/lib/android-apk.ts'

test('puts the android test apk next to the receiver page', () => {
  assert.equal(androidApkPath('/DashPi/receiver/'), '/DashPi/receiver/DashPi.apk')
})

test('offers that apk from the receiver landing', () => {
  const source = readFileSync(new URL('../src/components/install-landing.tsx', import.meta.url), 'utf8')
  assert.match(source, /안드로이드 앱 받기/)
  assert.match(source, /androidApkPath\(import\.meta\.env\?\.BASE_URL\)/)
  assert.match(source, /download="DashPi\.apk"/)
})

test('lets the apk download past the receiver service worker', () => {
  const config = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')
  assert.ok(config.includes('navigateFallbackDenylist: [/DashPi\\.apk$/]'))
})
