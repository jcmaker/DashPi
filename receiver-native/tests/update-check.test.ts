import assert from 'node:assert/strict'
import test from 'node:test'
import { checkForUpdate, isNewer, parseVersion, pickUpdate, type Release } from '../src/update-check.ts'

const apk = (tag: string) => ({
  name: 'DashPi.apk',
  browser_download_url: `https://github.com/jcmaker/DashPi/releases/download/${tag}/DashPi.apk`,
})
const release = (tag: string, extra: Partial<Release> = {}): Release => ({
  tag_name: tag, draft: false, prerelease: false, assets: [apk(tag)], ...extra,
})

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

test('picks the highest published app release that ships an APK', () => {
  const releases = [
    release('app-v1.0.1'),
    release('app-v1.2.0', { draft: true }),
    release('app-v1.1.0', { prerelease: true }),
    release('app-v1.0.3', { assets: [] }),
    release('landing-v9.0.0'),
    release('app-v1.0.2'),
  ]
  assert.deepEqual(pickUpdate(releases, '1.0.0'), {
    version: '1.0.2',
    url: apk('app-v1.0.2').browser_download_url,
  })
  assert.equal(pickUpdate(releases, '1.0.2'), null)
})

test('stays quiet when offline, rate-limited, or the version is unknown', async () => {
  const offline = async () => { throw new TypeError('Network request failed') }
  assert.equal(await checkForUpdate('1.0.0', offline), null)
  const limited = async () => new Response('{"message":"rate limit"}', { status: 403 })
  assert.equal(await checkForUpdate('1.0.0', limited), null)
  const never = async () => { throw new Error('must not fetch') }
  assert.equal(await checkForUpdate(null, never), null)
})

test('asks GitHub for releases and returns a newer one', async () => {
  let asked = ''
  const fetcher = async (url: string) => {
    asked = url
    return new Response(JSON.stringify([release('app-v2.0.0')]), { status: 200 })
  }
  assert.deepEqual(await checkForUpdate('1.4.2', fetcher), {
    version: '2.0.0',
    url: apk('app-v2.0.0').browser_download_url,
  })
  assert.equal(asked, 'https://api.github.com/repos/jcmaker/DashPi/releases?per_page=30')
})
