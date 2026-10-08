import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { describeSavedReports, prepareReportShare, saveVerifiedReport, shareSavedReport, type ReportStore } from '../src/saved-reports.ts'
import { parseTransferReport, REPORT_MEDIA_TYPE, verifyReportImages } from '../src/native-report.ts'
import { shareReportFile, type CacheFile } from '../src/share-report.ts'
import { unpackOpticalContainer, type OpticalFile } from '../src/unpack.ts'

const sha256 = async (value: Uint8Array) => new Uint8Array(createHash('sha256').update(value).digest())

const unpack = (data: Uint8Array) => unpackOpticalContainer(data, (body) => body, sha256)

function container(payload: Uint8Array, fileName = 'report.html', mediaType = 'text/html'): Uint8Array {
  const name = new TextEncoder().encode(fileName)
  const media = new TextEncoder().encode(mediaType)
  const data = new Uint8Array(49 + name.length + media.length + payload.length)
  data.set([0x44, 0x50, 0x43, 0x31, 0])
  const view = new DataView(data.buffer)
  view.setUint16(5, name.length, true)
  view.setUint16(7, media.length, true)
  view.setUint32(9, payload.length, true)
  view.setUint32(13, payload.length, true)
  data.set(createHash('sha256').update(payload).digest(), 17)
  data.set(name, 49)
  data.set(media, 49 + name.length)
  data.set(payload, 49 + name.length + media.length)
  return data
}

function memoryStore(backing = new Map<string, OpticalFile>()): ReportStore {
  return {
    put(name, mediaType, payload) {
      backing.set(name, { name, mediaType, payload: Uint8Array.from(payload) })
    },
    list() {
      return [...backing.values()].map((file) => ({
        name: file.name,
        mediaType: file.mediaType,
        size: file.payload.byteLength,
      }))
    },
    get(name) {
      const file = backing.get(name)
      if (!file) return undefined
      return { name: file.name, mediaType: file.mediaType, payload: Uint8Array.from(file.payload) }
    },
    remove(name) {
      backing.delete(name)
    },
    uri(name) {
      return backing.has(name) ? `document://dashpi-reports/files/${name}` : undefined
    },
  }
}

test('saves a SHA-256-verified file, lists it after a new store reads the same records, and deletes it', async () => {
  const records = new Map<string, OpticalFile>()
  const first = memoryStore(records)
  const payload = new TextEncoder().encode('<p>kept report</p>')
  const packed = container(payload)

  const saved = await saveVerifiedReport(packed, unpack, first)

  assert.equal(saved.name, 'report.html')
  assert.equal(saved.mediaType, 'text/html')
  assert.deepEqual(saved.payload, payload)
  assert.ok(packed.byteLength > payload.byteLength)

  const reopened = memoryStore(records)
  assert.deepEqual(reopened.list(), [{ name: 'report.html', mediaType: 'text/html', size: payload.byteLength }])
  assert.deepEqual(reopened.get('report.html'), saved)

  const other = new TextEncoder().encode('<p>other</p>')
  await saveVerifiedReport(container(other, 'other.html'), unpack, reopened)
  assert.deepEqual(
    reopened.list().map((item) => item.name),
    ['report.html', 'other.html'],
  )

  reopened.remove('report.html')
  assert.equal(reopened.get('report.html'), undefined)
  assert.deepEqual(reopened.list(), [{ name: 'other.html', mediaType: 'text/html', size: other.byteLength }])
  assert.deepEqual(first.get('other.html')?.payload, other)
})

test('refuses unverified bytes and does not store them', async () => {
  const store = memoryStore()
  const payload = new TextEncoder().encode('<p>tampered</p>')
  const packed = container(payload)
  packed[17] ^= 0xff
  const fragment = packed.slice(0, 20)

  await assert.rejects(saveVerifiedReport(packed, unpack, store), /sha256 mismatch/)
  await assert.rejects(saveVerifiedReport(fragment, unpack, store), /truncated container/)
  await assert.rejects(saveVerifiedReport(Uint8Array.from([1, 2, 3, 4]), unpack, store), /truncated container/)
  assert.deepEqual(store.list(), [])
})

test('refuses a verified-looking name that leaves the document directory', async () => {
  const store = memoryStore()
  const unpackUnsafe = async (): Promise<OpticalFile> => ({
    name: '../secret',
    mediaType: 'text/html',
    payload: Uint8Array.from([1]),
  })

  await assert.rejects(saveVerifiedReport(Uint8Array.from([1]), unpackUnsafe, store), /invalid container metadata/)
  assert.deepEqual(store.list(), [])
})

test('keeps the saved copy when sharing fails', async () => {
  const store = memoryStore()
  const payload = new TextEncoder().encode('<p>share later</p>')
  await saveVerifiedReport(container(payload), unpack, store)

  await assert.rejects(
    shareSavedReport('report.html', store, async () => {
      throw new Error('share failed')
    }),
    /share failed/,
  )

  assert.deepEqual(store.get('report.html')?.payload, payload)
  assert.equal(store.uri('report.html'), 'document://dashpi-reports/files/report.html')
})

const imageHash = async (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex')
function reportPayload(triggeredAt = '2026-10-08T01:02:03+00:00'): Uint8Array {
  const jpeg = Uint8Array.from([0xff, 0xd8, 0xff, 0xd9])
  return new TextEncoder().encode(JSON.stringify({
    format: 'dashpi.report', version: 1, incident_id: 'ab'.repeat(16),
    triggered_at: triggeredAt, generated_at: '2026-10-08T02:03:04+00:00',
    model: 'test', incident_timestamp: 2, summary: '요약 첫 줄\n다음 줄',
    observations: [{ timestamp: 2, description: '사고 순간' }],
    limitations: [], warnings: [], major_negligence_review: {},
    keyframes: ['before', 'moment', 'after'].map((role, timestamp) => ({
      role, timestamp, jpeg_base64: Buffer.from(jpeg).toString('base64'),
      sha256: createHash('sha256').update(jpeg).digest('hex'),
    })),
    digests: { 'clip.mp4': 'cd'.repeat(32) },
  }))
}

test('mixed saved list shows newest incidents, verified thumbnail, old names, and independently unreadable rows', async () => {
  const store = memoryStore()
  store.put('z-old.json', REPORT_MEDIA_TYPE, reportPayload('2026-10-07T01:02:03+00:00'))
  store.put('a-new.json', REPORT_MEDIA_TYPE, reportPayload())
  store.put('broken.json', REPORT_MEDIA_TYPE, new TextEncoder().encode('{}'))
  store.put('old.html', 'text/html', new TextEncoder().encode('<p>old</p>'))
  store.put('read-failure.json', REPORT_MEDIA_TYPE, reportPayload())
  const get = store.get
  store.get = (name) => {
    if (name === 'read-failure.json') throw new Error('read denied')
    return get(name)
  }
  const rows = await describeSavedReports(store, imageHash)
  assert.deepEqual(rows.map((row) => row.name), ['a-new.json', 'z-old.json', 'broken.json', 'old.html', 'read-failure.json'])
  assert.equal(rows[0].triggeredAt, '2026-10-08T01:02:03+00:00')
  assert.equal(rows[0].summary, '요약 첫 줄')
  assert.match(rows[0].thumbnailUri!, /^data:image\/jpeg;base64,/)
  assert.equal(rows[2].unreadable, true)
  assert.equal(rows[4].unreadable, true)
  assert.equal(rows[3].summary, undefined)
  store.remove('broken.json')
  assert.equal((await describeSavedReports(store, imageHash)).some((row) => row.name === 'broken.json'), false)
})

test('a corrupted moment image leaves the saved incident readable without a thumbnail', async () => {
  const value = JSON.parse(new TextDecoder().decode(reportPayload()))
  value.keyframes[1].sha256 = '00'.repeat(32)
  const store = memoryStore()
  store.put('report.json', REPORT_MEDIA_TYPE, new TextEncoder().encode(JSON.stringify(value)))
  const rows = await describeSavedReports(store, imageHash)
  assert.equal(rows[0].triggeredAt, value.triggered_at)
  assert.equal(rows[0].thumbnailUri, undefined)
  assert.equal(rows[0].unreadable, undefined)
})

test('listing leaves legacy HTML and video payloads unopened while enriching JSON', async () => {
  const store = memoryStore()
  store.put('legacy.html', 'text/html', new Uint8Array())
  store.put('legacy.mp4', 'video/mp4', new Uint8Array())
  store.put('native.json', REPORT_MEDIA_TYPE, reportPayload())
  const get = store.get
  const reads: string[] = []
  store.get = (name) => {
    reads.push(name)
    if (name !== 'native.json') throw new Error('legacy payload must stay unopened')
    return get(name)
  }
  const rows = await describeSavedReports(store, imageHash)
  assert.deepEqual(reads, ['native.json'])
  assert.deepEqual(rows.map((row) => row.name), ['native.json', 'legacy.html', 'legacy.mp4'])
  assert.equal(rows[0].summary, '요약 첫 줄')
  assert.match(rows[0].thumbnailUri!, /^data:image\/jpeg;base64,/)
  assert.equal(rows[1].unreadable, undefined)
  assert.equal(rows[2].unreadable, undefined)
})

test('sharing creates HTML separately and keeps original bytes through cancellation, failure, and retry', async () => {
  const store = memoryStore()
  const source = reportPayload()
  store.put('original.json', REPORT_MEDIA_TYPE, source)
  const file = store.get('original.json')!
  const prepared = await prepareReportShare(file, imageHash)
  assert.equal(prepared.name, `dashpi-${'ab'.repeat(16)}.html`)
  assert.equal(prepared.mediaType, 'text/html')
  assert.match(new TextDecoder().decode(prepared.payload), /<!doctype html>/)
  const malformed = { ...file, payload: new TextEncoder().encode('{}') }
  assert.equal(await prepareReportShare(malformed, imageHash), malformed)
  const old = { ...file, name: 'old.html', mediaType: 'text/html' }
  assert.equal(await prepareReportShare(old, imageHash), old)

  let cachePayload: Uint8Array | undefined
  const cache: CacheFile = {
    name: `${'12'.repeat(16)}.html`, uri: 'cache://share',
    get exists() { return cachePayload !== undefined },
    write(bytes) { cachePayload = Uint8Array.from(bytes) },
    bytes() { return cachePayload! },
    delete() { cachePayload = undefined },
  }
  const share = (fail: boolean) => shareReportFile({
    reportName: prepared.name, mediaType: prepared.mediaType, payload: prepared.payload,
    randomId: '12'.repeat(16), openCacheFile: () => cache,
    present: async () => {
      if (fail) throw new Error('share rejected')
      return { outcome: 'dismissed' }
    },
  })
  await share(false)
  assert.equal(cache.exists, false)
  assert.deepEqual(store.get(file.name)!.payload, source)
  await assert.rejects(share(true), /share rejected/)
  assert.equal(cache.exists, false)
  assert.deepEqual(store.get(file.name)!.payload, source)
  await share(false)
  assert.deepEqual(store.get(file.name)!.payload, source)
})

test('native decoder failures are retained in the generated share document', async () => {
  const file = { name: 'report.json', mediaType: REPORT_MEDIA_TYPE, payload: reportPayload() }
  const report = await verifyReportImages(parseTransferReport(file.payload), imageHash)
  report.keyframes = report.keyframes.map((frame) => ({ ...frame, imageValid: false, imageError: '이미지 손상', dataUri: null }))
  const shared = await prepareReportShare(file, imageHash, report)
  const html = new TextDecoder().decode(shared.payload)
  assert.match(html, /이미지 손상/)
  assert.doesNotMatch(html, /<img\b/)
  assert.deepEqual(file.payload, reportPayload())
})
