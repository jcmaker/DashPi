import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  isShareCacheName,
  randomShareId,
  SHARE_CACHE_DIRECTORY,
  shareCacheName,
  shareFileStillNeeded,
  shareReportFile,
  type CacheFile,
} from '../src/share-report.ts'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

function memoryCache() {
  const files = new Map<string, Uint8Array | null>()
  return {
    open(name: string): CacheFile {
      return {
        name,
        uri: `file:///cache/${SHARE_CACHE_DIRECTORY}/${name}`,
        get exists() {
          return files.get(name) != null
        },
        write(payload: Uint8Array) {
          files.set(name, Uint8Array.from(payload))
        },
        bytes() {
          const stored = files.get(name)
          if (!stored) throw new Error(`missing ${name}`)
          return stored
        },
        delete() {
          files.set(name, null)
        },
      }
    },
  }
}

const htmlId = 'ab'.repeat(16)
const otherId = 'cd'.repeat(16)

test('cache name is random and is not the report name', () => {
  const name = shareCacheName('report.html', htmlId)
  assert.equal(name, `${htmlId}.html`)
  assert.equal(name.includes('report'), false)
  assert.equal(isShareCacheName(name), true)
  assert.equal(isShareCacheName('report.html'), false)
  assert.equal(isShareCacheName('../report.html'), false)
  assert.notEqual(shareCacheName('report.html', htmlId), shareCacheName('report.html', otherId))
  assert.equal(shareCacheName('notes', htmlId), htmlId)
  assert.equal(shareCacheName('Report.HTML', htmlId), `${htmlId}.html`)
  assert.throws(() => shareCacheName('report.html', 'report'))
  assert.throws(() => shareCacheName(`${htmlId}.html`, htmlId))
})

test('random ids are 128-bit hex and do not depend on the report name', () => {
  const first = randomShareId((bytes) => bytes.fill(1))
  const second = randomShareId((bytes) => bytes.fill(2))
  assert.match(first, /^[0-9a-f]{32}$/)
  assert.notEqual(first, second)
  assert.equal(first.includes('report'), false)
  const live = randomShareId()
  assert.notEqual(live, randomShareId())
  assert.equal(shareCacheName('report.html', live).includes('report'), false)
})

test('the picked share receives the same bytes and media type, then the cache file is removed', async () => {
  const cache = memoryCache()
  const payload = Uint8Array.from([1, 2, 3, 4])
  let seen: { name: string; mediaType: string; bytes: Uint8Array } | undefined
  await shareReportFile({
    reportName: 'report.html',
    mediaType: 'text/html',
    payload,
    randomId: htmlId,
    openCacheFile: cache.open,
    present: async (file, mediaType) => {
      payload[0] = 9
      seen = { name: file.name, mediaType, bytes: file.bytes() }
      assert.equal(file.exists, true)
      assert.equal(shareFileStillNeeded(file.name), true)
    },
  })
  assert.equal(seen?.name, `${htmlId}.html`)
  assert.equal(seen?.mediaType, 'text/html')
  assert.deepEqual(seen?.bytes, Uint8Array.from([1, 2, 3, 4]))
  assert.equal(cache.open(seen!.name).exists, false)
  assert.equal(shareFileStillNeeded(seen!.name), false)
})

test('a rejected share still removes only that cache file', async () => {
  const cache = memoryCache()
  const kept = cache.open('aa'.repeat(16) + '.html')
  kept.write(Uint8Array.from([7]))
  await assert.rejects(
    shareReportFile({
      reportName: 'report.html',
      mediaType: 'text/html',
      payload: Uint8Array.from([1]),
      randomId: otherId,
      openCacheFile: cache.open,
      present: async () => {
        throw new Error('sheet failed')
      },
    }),
    /sheet failed/,
  )
  assert.equal(cache.open(`${otherId}.html`).exists, false)
  assert.deepEqual(kept.bytes(), Uint8Array.from([7]))
})

test('does not delete a share file that is still needed', async () => {
  const cache = memoryCache()
  const keptName = shareCacheName('report.html', htmlId)
  let release: () => void = () => {}
  const first = shareReportFile({
    reportName: 'report.html',
    mediaType: 'text/html',
    payload: Uint8Array.from([1, 2]),
    randomId: htmlId,
    openCacheFile: cache.open,
    present: () =>
      new Promise<void>((resolve) => {
        release = resolve
      }),
  })
  assert.equal(cache.open(keptName).exists, true)
  assert.equal(shareFileStillNeeded(keptName), true)
  await assert.rejects(
    shareReportFile({
      reportName: 'report.html',
      mediaType: 'text/html',
      payload: Uint8Array.from([9]),
      randomId: htmlId,
      openCacheFile: () => {
        throw new Error('opened the in-flight cache file')
      },
      present: async () => {},
    }),
    (error: unknown) => error instanceof Error && error.message === 'share file is still needed',
  )
  assert.deepEqual(cache.open(keptName).bytes(), Uint8Array.from([1, 2]))

  await assert.rejects(
    shareReportFile({
      reportName: 'clip.bin',
      mediaType: 'application/octet-stream',
      payload: Uint8Array.from([3]),
      randomId: otherId,
      openCacheFile: cache.open,
      present: async () => {
        throw new Error('busy')
      },
    }),
    /busy/,
  )
  assert.equal(cache.open(`${otherId}.bin`).exists, false)
  assert.equal(cache.open(keptName).exists, true)

  let held = true
  const heldName = shareCacheName('photo.png', 'ef'.repeat(16))
  await shareReportFile({
    reportName: 'photo.png',
    mediaType: 'image/png',
    payload: Uint8Array.from([4, 5]),
    randomId: 'ef'.repeat(16),
    openCacheFile: cache.open,
    present: async (file, mediaType) => {
      assert.equal(mediaType, 'image/png')
      assert.equal(file.name, heldName)
    },
    stillNeeded: () => held,
  })
  assert.equal(cache.open(heldName).exists, true)
  assert.equal(cache.open(keptName).exists, true)

  release()
  await first
  assert.equal(cache.open(keptName).exists, false)
  assert.equal(cache.open(heldName).exists, true)
  assert.equal(shareFileStillNeeded(keptName), false)
  assert.equal(shareFileStillNeeded(heldName), false)
})

test('android share path grants read on the chooser and revokes it when the sheet finishes', () => {
  const kotlin = readFileSync(
    join(root, 'modules/dashpi-share/android/src/main/java/expo/modules/dashpishare/DashpiShareModule.kt'),
    'utf8',
  )
  const paths = readFileSync(join(root, 'modules/dashpi-share/android/src/main/res/xml/dashpi_share_paths.xml'), 'utf8')
  const plugin = readFileSync(join(root, 'modules/dashpi-share/app.plugin.js'), 'utf8')
  assert.equal(kotlin.includes('grantUriPermission('), false)
  assert.equal(kotlin.includes('queryIntentActivities'), false)
  assert.equal(kotlin.match(/addFlags\(Intent\.FLAG_GRANT_READ_URI_PERMISSION\)/g)?.length, 2)
  assert.match(kotlin, /Intent\.createChooser/)
  assert.match(kotlin, /clipData/)
  assert.match(kotlin, /revokeUriPermission/)
  assert.match(kotlin, /file\.delete\(\)/)
  assert.match(kotlin, /SHARE_CACHE_DIRECTORY = "dashpi-share"/)
  assert.equal(paths.includes('path="."'), false)
  assert.match(paths, /path="dashpi-share\/"/)
  assert.match(plugin, /android:exported': 'false'/)
  assert.match(plugin, /android:grantUriPermissions': 'true'/)
  assert.equal(plugin.includes('queryIntentActivities'), false)
})
