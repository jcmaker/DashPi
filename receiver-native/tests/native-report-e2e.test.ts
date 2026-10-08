import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { FrameCollector } from '../../web/src/optical/collector.ts'
import { parseFrame } from '../../web/src/optical/protocol.ts'
import { handleBarcodeScan } from '../src/barcode.ts'
import { inflateBounded } from '../src/inflate-bounded.ts'
import { nearestKeyframe, REPORT_MEDIA_TYPE, verifyReportImages } from '../src/native-report.ts'
import { previewForFile } from '../src/preview-model.ts'
import { renderReportHtml } from '../src/report-html.ts'
import { unpackOpticalContainer } from '../src/unpack.ts'

type Fixture = {
  name: string
  media_type: string
  payload: string
  payload_sha256: string
  payload_length: number
  container_length: number
  block_count: number
  block_size: number
  late_start_sequence: number
  sequences: number[]
  frames_hex: string[]
}
const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/optical-report-v1.json', import.meta.url), 'utf8')) as Fixture
const sha256 = async (input: Uint8Array) => new Uint8Array(createHash('sha256').update(input).digest())

function reconstruct(): Uint8Array {
  const collector = new FrameCollector()
  for (const hex of fixture.frames_hex) {
    const bytes = Buffer.from(hex, 'hex')
    const frame = parseFrame(bytes)
    assert.ok(frame.sequence >= fixture.late_start_sequence, 'receiver joined after the first two systematic passes')
    const result = handleBarcodeScan(collector, { data: 'null', rawBytesBase64: bytes.toString('base64') })
    assert.ok(result.status === 'progress' || result.status === 'done', 'every Python frame passes CRC and protocol checks')
    if (result.status === 'done') {
      assert.equal(result.recovered, fixture.block_count)
      return result.packed
    }
  }
  throw new Error('Python repair frames did not reconstruct the native report')
}

test('Python JPEG report survives late joining, shuffled frames, duplicates and loss through native HTML export', async () => {
  assert.ok(fixture.payload_length <= 60_000)
  assert.equal(fixture.block_size, 512)
  assert.ok(new Set(fixture.sequences).size < fixture.sequences.length, 'fixture includes duplicates')
  assert.ok(fixture.sequences.some((sequence, index) => index > 0 && sequence < fixture.sequences[index - 1]), 'fixture includes reordering')
  assert.ok(fixture.sequences.some((sequence) => sequence > fixture.late_start_sequence + fixture.block_count), 'fixture includes fountain repair symbols')
  const packed = reconstruct()
  assert.equal(packed.length, fixture.container_length)
  const file = await unpackOpticalContainer(packed, inflateBounded, sha256)
  assert.equal(file.name, fixture.name)
  assert.equal(file.mediaType, REPORT_MEDIA_TYPE)
  assert.equal(file.payload.length, fixture.payload_length)
  assert.equal(new TextDecoder().decode(file.payload), fixture.payload)
  assert.equal(createHash('sha256').update(file.payload).digest('hex'), fixture.payload_sha256)
  const preview = previewForFile(file)
  assert.equal(preview.kind, 'native-report')
  if (preview.kind !== 'native-report') return
  const report = await verifyReportImages(preview.report, async (bytes) => createHash('sha256').update(bytes).digest('hex'))
  assert.ok(report.keyframes.every((frame) => frame.imageValid))
  assert.equal(nearestKeyframe(report.observations[0].timestamp, report.keyframes), 'moment')
  const html = renderReportHtml(report)
  assert.equal((html.match(/<img /g) ?? []).length, 3)
  assert.match(html, /&lt;태그&gt; &amp; 인용/)
  assert.equal(html.includes('<script'), false)
  assert.equal(html.includes(report.digests['clip.mp4']), true)
})

test('native container rejects an altered SHA-256 before JSON preview or saving', async () => {
  const packed = reconstruct()
  packed[17] ^= 0xff
  await assert.rejects(unpackOpticalContainer(packed, inflateBounded, sha256), /sha256 mismatch/)
})
