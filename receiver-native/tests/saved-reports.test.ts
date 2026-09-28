import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { saveVerifiedReport, shareSavedReport, type ReportStore } from '../src/saved-reports.ts'
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
