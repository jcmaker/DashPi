import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'

const pako = createRequire(import.meta.url)('pako') as {
  deflate: (data: Uint8Array) => Uint8Array
  inflate: (data: Uint8Array) => Uint8Array
}
import { bytesFromBarcode, handleBarcodeScan, type BarcodeScan } from '../src/barcode.ts'
import { unpackOpticalContainer } from '../src/unpack.ts'
import { FrameCollector } from '../../web/src/optical/collector.ts'

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

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function packFrame(
  sessionId: number,
  sequence: number,
  blockCount: number,
  blockSize: number,
  totalLength: number,
  indices: number[],
  symbol: Uint8Array,
): Uint8Array {
  const data = new Uint8Array(23 + indices.length * 2 + blockSize + 4)
  data.set([0x44, 0x50, 0x51, 0x31, 1, 0])
  const view = new DataView(data.buffer)
  view.setUint32(6, sessionId, true)
  view.setUint32(10, sequence, true)
  view.setUint16(14, blockCount, true)
  view.setUint16(16, blockSize, true)
  view.setUint32(18, totalLength, true)
  view.setUint8(22, indices.length)
  indices.forEach((index, position) => view.setUint16(23 + position * 2, index, true))
  data.set(symbol, 23 + indices.length * 2)
  view.setUint32(data.length - 4, crc32(data.subarray(0, -4)), true)
  return data
}

function systematicFrames(packed: Uint8Array, blockSize: number): Uint8Array[] {
  const blockCount = Math.ceil(packed.length / blockSize)
  return Array.from({ length: blockCount }, (_, sequence) => {
    const symbol = new Uint8Array(blockSize)
    symbol.set(packed.subarray(sequence * blockSize, sequence * blockSize + blockSize))
    return packFrame(7, sequence, blockCount, blockSize, packed.length, [sequence], symbol)
  })
}

function isUtf8(bytes: Uint8Array): boolean {
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    return true
  } catch {
    return false
  }
}

// Kotlin `null.toString()` is the string "null". `String(rawBytes)` is UTF-8 with U+FFFD.
function androidScan(frame: Uint8Array, display: 'null' | 'utf8'): BarcodeScan {
  const raw = new TextDecoder().decode(frame)
  return {
    data: display === 'null' ? 'null' : raw,
    raw,
    rawBytesBase64: Buffer.from(frame).toString('base64'),
  }
}

function legacyBytes(scan: BarcodeScan): Uint8Array | undefined {
  try {
    return bytesFromBarcode({ data: scan.data, raw: scan.raw })
  } catch {
    return undefined
  }
}

test('recovers a non-UTF-8 frame when display text is null or UTF-8-corrupted', () => {
  const payload = Uint8Array.of(0xff, 0xfe, 0xc3, 0x28, 0x80)
  const frames = systematicFrames(container(payload, payload, 0), 32)
  const frame = frames.find((candidate) => !isUtf8(candidate))
  assert.ok(frame)

  for (const display of ['null', 'utf8'] as const) {
    const scan = androidScan(frame, display)
    assert.notDeepEqual(legacyBytes(scan), frame)
    assert.notEqual(handleBarcodeScan(new FrameCollector(), { data: scan.data, raw: scan.raw }).status, 'progress')
    assert.throws(() => bytesFromBarcode(scan.raw ?? ''), /not byte data/)
    const bytes = bytesFromBarcode(scan)
    assert.deepEqual(bytes, frame)
    assert.equal(handleBarcodeScan(new FrameCollector(), scan).status, 'progress')
  }
})

test('systematic frames from raw bytes increase recovered and pass SHA-256', async () => {
  const payload = Uint8Array.of(0xff, 0xfe, 0x00, 0xc3, 0x28, 0x80, 0x41, 0x42)
  const packed = container(payload, payload, 0)
  const frames = systematicFrames(packed, 32)
  assert.ok(frames.length > 1)
  assert.ok(frames.some((frame) => !isUtf8(frame)))

  const collector = new FrameCollector()
  let done: Uint8Array | undefined
  for (const [index, frame] of frames.entries()) {
    const outcome = handleBarcodeScan(collector, androidScan(frame, index % 2 === 0 ? 'null' : 'utf8'))
    if (index < frames.length - 1) {
      assert.equal(outcome.status, 'progress')
      if (outcome.status === 'progress') assert.equal(outcome.recovered, index + 1)
      continue
    }
    assert.equal(outcome.status, 'done')
    if (outcome.status === 'done') {
      assert.equal(outcome.recovered, frames.length)
      done = outcome.packed
    }
  }

  const file = await unpackOpticalContainer(done!, (body) => body, sha256)
  assert.deepEqual(file.payload, payload)
})

test('drops a CRC-bad frame without an error', () => {
  const payload = Uint8Array.of(0xff, 0x10, 0x20, 0x30)
  const [frame] = systematicFrames(container(payload, payload, 0), 32)
  assert.ok(frame)
  const collector = new FrameCollector()
  assert.equal(handleBarcodeScan(collector, androidScan(frame, 'null')).status, 'progress')

  const broken = Uint8Array.from(frame)
  broken[broken.length - 1] ^= 0xff
  const outcome = handleBarcodeScan(collector, androidScan(broken, 'null'))
  assert.equal(outcome.status, 'drop')
  assert.equal(collector.progress.recovered, 1)
})

test('expo-camera Android forwards ML Kit rawBytes as base64', () => {
  const root = new URL('../node_modules/expo-camera/android/src/main/java/expo/modules/camera/', import.meta.url)
  const event = readFileSync(new URL('common/CommonEvents.kt', root), 'utf8')
  const view = readFileSync(new URL('ExpoCameraView.kt', root), 'utf8')
  const analyzer = readFileSync(new URL('analyzers/BarcodeAnalyzer.kt', root), 'utf8')
  assert.match(event, /rawBytesBase64/)
  assert.match(view, /rawBytesBase64 = barcode\.rawBytes\?\.let \{ android\.util\.Base64\.encodeToString/)
  assert.match(view, /event\.rawBytesBase64 \?: event\.data/)
  assert.match(analyzer, /barcode\.rawBytes\?\.copyOf\(\)/)
  // expo-camera ships a prebuilt AAR; without this, Gradle links it and the patched source never ships.
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
  assert.ok(pkg.expo?.autolinking?.android?.buildFromSource?.includes('expo-camera'))
})
