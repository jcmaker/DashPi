import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import test from 'node:test'

const pako = createRequire(import.meta.url)('pako') as {
  deflate: (data: Uint8Array) => Uint8Array
  inflate: (data: Uint8Array) => Uint8Array
}
import { bytesFromBarcode } from '../src/barcode.ts'
import { unpackOpticalContainer } from '../src/unpack.ts'

const sha256 = async (value: Uint8Array) => new Uint8Array(createHash('sha256').update(value).digest())

function container(payload: Uint8Array, body: Uint8Array, flags: number, fileName = 'report.html'): Uint8Array {
  const name = new TextEncoder().encode(fileName)
  const media = new TextEncoder().encode('text/html')
  const data = new Uint8Array(49 + name.length + media.length + body.length)
  data.set([0x44, 0x50, 0x43, 0x31, flags])
  const view = new DataView(data.buffer)
  view.setUint16(5, name.length, true)
  view.setUint16(7, media.length, true)
  view.setUint32(9, payload.length, true)
  view.setUint32(13, body.length, true)
  data.set(createHash('sha256').update(payload).digest(), 17)
  data.set(name, 49)
  data.set(media, 49 + name.length)
  data.set(body, 49 + name.length + media.length)
  return data
}

test('keeps QR byte-mode characters as the original frame bytes', () => {
  assert.deepEqual(bytesFromBarcode('DPQ1\u0000\u00ff'), Uint8Array.from([68, 80, 81, 49, 0, 255]))
  assert.throws(() => bytesFromBarcode('한'), /not byte data/)
})

test('checks an uncompressed container the same way as the web receiver', async () => {
  const payload = new TextEncoder().encode('<p>ok</p>')
  const file = await unpackOpticalContainer(container(payload, payload, 0), (body) => body, sha256)
  assert.equal(file.name, 'report.html')
  assert.equal(file.mediaType, 'text/html')
  assert.deepEqual(file.payload, payload)
})

test('rejects a download name that leaves the received file', async () => {
  const payload = new TextEncoder().encode('ok'.repeat(40))
  await assert.rejects(
    unpackOpticalContainer(container(payload, payload, 0, '../report.html'), (body) => body, sha256),
    /invalid container metadata/,
  )
})

test('inflates a compressed container and rejects a bad hash', async () => {
  const payload = new TextEncoder().encode('ok'.repeat(200))
  const body = pako.deflate(payload)
  assert.ok(body.length < payload.length)
  const file = await unpackOpticalContainer(container(payload, body, 1), (value) => pako.inflate(value), sha256)
  assert.deepEqual(file.payload, payload)

  const broken = container(payload, body, 1)
  broken[17] ^= 0xff
  await assert.rejects(unpackOpticalContainer(broken, (value) => pako.inflate(value), sha256), /sha256 mismatch/)
})
