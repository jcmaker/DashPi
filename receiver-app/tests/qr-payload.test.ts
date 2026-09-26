import assert from 'node:assert/strict'
import test from 'node:test'
import zxing from '@zxing/library'
import QRCode from 'qrcode'
import fixture from '../../tests/fixtures/optical-e2e.json' with { type: 'json' }
import { qrPayload } from '../../web/src/optical/collector.ts'
import { parseFrame } from '../../web/src/optical/protocol.ts'

const {
  BinaryBitmap,
  DecodeHintType,
  HybridBinarizer,
  QRCodeReader,
  ResultMetadataType,
  RGBLuminanceSource,
} = zxing

function decodeQrImage(bytes: Uint8Array) {
  const { modules } = QRCode.create([{ data: bytes, mode: 'byte' }], { errorCorrectionLevel: 'L' })
  const scale = 4
  const quiet = 4
  const size = (modules.size + quiet * 2) * scale
  const luminance = new Uint8ClampedArray(size * size).fill(255)
  for (let y = 0; y < modules.size; y += 1) {
    for (let x = 0; x < modules.size; x += 1) {
      if (!modules.get(y, x)) continue
      for (let dy = 0; dy < scale; dy += 1) {
        const row = ((y + quiet) * scale + dy) * size
        luminance.fill(0, row + (x + quiet) * scale, row + (x + quiet + 1) * scale)
      }
    }
  }
  const source = new RGBLuminanceSource(luminance, size, size, size, size, 0, 0)
  const hints = new Map([[DecodeHintType.TRY_HARDER, true]])
  return new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(source)), hints)
}

test('recovers the exact DashPi frame bytes from a camera-style QR decode', () => {
  const frame = Uint8Array.from(Buffer.from(fixture.frames_hex[0], 'hex'))
  const result = decodeQrImage(frame)

  assert.notDeepEqual(Uint8Array.from(result.getRawBytes()), frame)
  const payload = qrPayload(result.getResultMetadata()?.get(ResultMetadataType.BYTE_SEGMENTS))
  assert.deepEqual(payload, frame)
  assert.equal(parseFrame(payload!).blockCount, parseFrame(frame).blockCount)
})

test('ignores QR codes without byte segments', () => {
  assert.equal(qrPayload(undefined), undefined)
  assert.equal(qrPayload([]), undefined)
  assert.equal(qrPayload(['text']), undefined)
})
