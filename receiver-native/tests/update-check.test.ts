import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  UPDATE_CHECK_INTERVAL_MS,
  checkForUpdate,
  isNewer,
  parseVersion,
  updateCooldown,
} from '../src/update-check.ts'

const APK_URL = 'https://jcmaker.github.io/DashPi/receiver/DashPi.apk?v=2.0.0'

test('parses plain and app-tagged semantic versions', () => {
  assert.deepEqual(parseVersion('1.2.3'), [1, 2, 3])
  assert.deepEqual(parseVersion('app-v1.10.0'), [1, 10, 0])
  assert.equal(parseVersion('v1.2'), null)
  assert.equal(parseVersion('landing-2026'), null)
})

test('compares versions numerically, not as text', () => {
  assert.equal(isNewer('1.10.0', '1.9.9'), true)
  assert.equal(isNewer('1.0.0', '1.0.0'), false)
  assert.equal(isNewer('0.9.0', '1.0.0'), false)
  assert.equal(isNewer('1.0.1', 'garbage'), false)
})

test('stays quiet when offline, rate-limited, or the version is unknown', async () => {
  const offline = async () => { throw new TypeError('Network request failed') }
  assert.equal(await checkForUpdate('1.0.0', offline), null)
  const limited = async () => new Response('{"message":"rate limit"}', { status: 403 })
  assert.equal(await checkForUpdate('1.0.0', limited), null)
  const never = async () => { throw new Error('must not fetch') }
  assert.equal(await checkForUpdate(null, never), null)
})

test('a failed check does not block an immediate retry', () => {
  const now = 1_700_000_000_000
  // Failure and "no newer release" both leave the dialog unshown.
  const missed = updateCooldown(0, now, false)
  assert.equal(missed.shownAt, 0)
  assert.equal(missed.due, true)
  assert.equal(updateCooldown(missed.shownAt, now + 1, false).due, true)

  const shown = updateCooldown(0, now, true)
  assert.equal(shown.shownAt, now)
  assert.equal(shown.due, false)
  assert.equal(updateCooldown(shown.shownAt, now + UPDATE_CHECK_INTERVAL_MS - 1, false).due, false)
  assert.equal(updateCooldown(shown.shownAt, now + UPDATE_CHECK_INTERVAL_MS, false).due, true)
})

test('offers the Pages APK only after Pages advertises a newer version', async () => {
  let asked = ''
  const fetcher = async (url: string) => {
    asked = url
    return new Response(JSON.stringify({ version: '2.0.0' }), { status: 200 })
  }
  assert.deepEqual(await checkForUpdate('1.4.2', fetcher), {
    version: '2.0.0',
    url: APK_URL,
  })
  assert.equal(asked, 'https://jcmaker.github.io/DashPi/receiver/version.json')
  assert.equal(await checkForUpdate('2.0.0', fetcher), null)
  const invalid = async () => new Response(JSON.stringify({ version: 'unknown' }), { status: 200 })
  assert.equal(await checkForUpdate('1.4.2', invalid), null)
})

test('the update button opens the APK in Chrome on Android, else the default browser', () => {
  const app = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
  const module = readFileSync(
    new URL('../modules/dashpi-share/android/src/main/java/expo/modules/dashpishare/DashpiShareModule.kt', import.meta.url),
    'utf8',
  )
  assert.match(app, /onPress: \(\) => void openUpdate\(update\.url\)/)
  assert.match(app, /openInChrome\(url\)\.catch\(\(\) => false\)\)\) return\n\s+await Linking\.openURL\(url\)/)
  assert.match(module, /setPackage\("com\.android\.chrome"\)/)
  assert.match(module, /uri\.scheme != "https"/)
  assert.match(module, /catch \(error: ActivityNotFoundException\) \{\s+false/)
})
