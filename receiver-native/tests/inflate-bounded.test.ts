import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import test from 'node:test'
import { inflateBounded } from '../src/inflate-bounded.ts'
import { unpackOpticalContainer } from '../src/unpack.ts'

const pako = createRequire(import.meta.url)('pako') as {
  deflate: (data: Uint8Array) => Uint8Array
}

const sha256 = async (value: Uint8Array) => new Uint8Array(createHash('sha256').update(value).digest())

function container(payload: Uint8Array, body: Uint8Array, flags: number): Uint8Array {
  const name = new TextEncoder().encode('report.html')
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

test('inflates a report under the limit and matches SHA-256', async () => {
  const payload = new TextEncoder().encode('<p>offline report</p>'.repeat(40))
  const body = pako.deflate(payload)
  assert.ok(body.length < payload.length)

  const file = await unpackOpticalContainer(container(payload, body, 1), inflateBounded, sha256)

  assert.equal(file.name, 'report.html')
  assert.equal(file.mediaType, 'text/html')
  assert.deepEqual(file.payload, payload)
  assert.equal(
    createHash('sha256').update(file.payload).digest('hex'),
    createHash('sha256').update(payload).digest('hex'),
  )
})

test('stops inflation when the declared length is only just above the compressed body', () => {
  const huge = Buffer.alloc(8 * 1024 * 1024, 0x61)
  const body = pako.deflate(huge)
  const declared = body.length + 1
  const NativeUint8Array = globalThis.Uint8Array
  let allocated = 0
  globalThis.Uint8Array = class extends NativeUint8Array {
    constructor(value?: ArrayBuffer | ArrayLike<number> | number) {
      super(value as ArrayBuffer)
      if (typeof value === 'number') allocated += value
    }
  }

  let caught: unknown
  try {
    inflateBounded(body, declared)
  } catch (error) {
    caught = error
  } finally {
    globalThis.Uint8Array = NativeUint8Array
  }

  assert.ok(caught instanceof Error)
  assert.match(caught.message, /invalid container length/)
  assert.ok(allocated > 0)
  assert.ok(allocated < huge.length / 8, `inflated ${allocated} bytes`)
})
