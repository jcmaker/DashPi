import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import {
  IMAGE_DAMAGED, MAX_REPORT_IMAGE_BYTES, REPORT_MEDIA_TYPE, REPORT_OPEN_FAILED, REVIEW_ITEMS,
  nearestKeyframe, parseTransferReport, relativeTimestamp, verifyReportImages,
} from '../src/native-report.ts'
import { previewForFile } from '../src/preview-model.ts'
import { renderReportHtml } from '../src/report-html.ts'

const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x12, 0x34, 0xff, 0xd9])
const hash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex')
const sha256 = async (bytes: Uint8Array) => hash(bytes)
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))

test('print report expands all review and evidence details and includes all verified photos', async () => {
  const report = await verifyReportImages(parseTransferReport(encode(fixture())), sha256)
  const html = renderReportHtml(report, 'print')
  assert.match(html, /<details open><summary>12개 항목 모두 보기/)
  assert.match(html, /<details class="evidence" open>/)
  assert.equal((html.match(/<img /g) ?? []).length, 3)
  for (const [, label] of REVIEW_ITEMS) assert.ok(html.includes(label))
  assert.match(html, /@page\{size:A4;margin:14mm\}/)
  assert.match(html, /원본 클립 SHA-256/)
  assert.doesNotMatch(html, /<script\b/)
})

function fixture() {
  return {
    format: 'dashpi.report', version: 1, incident_id: 'incident-1234',
    triggered_at: '2026-10-04T13:00:02+09:00', generated_at: '2026-10-04T04:01:00.123456Z',
    model: 'model-one', incident_timestamp: 2, summary: '차량 접촉 장면',
    observations: [{ timestamp: 1, description: '차량 접근' }, { timestamp: 2, description: '차량 접촉' }],
    limitations: ['영상 밖은 확인할 수 없습니다.'], warnings: ['추정 시각'],
    major_negligence_review: Object.fromEntries(REVIEW_ITEMS.map(([key]) => [key, {
      status: 'not_observed', evidence: '관련 장면 없음', timestamp: null,
    }])),
    keyframes: ['before', 'moment', 'after'].map((role, index) => ({
      role, timestamp: index * 2, jpeg_base64: jpeg.toString('base64'), sha256: hash(jpeg),
    })),
    digests: { 'clip.mp4': '1'.repeat(64) },
  }
}

test('valid report preserves the transfer schema and verifies all three JPEGs', async () => {
  const report = parseTransferReport(encode(fixture()))
  assert.equal(report.incident_id, 'incident-1234')
  assert.equal(report.major_negligence_review.signal.status, 'not_observed')
  const verified = await verifyReportImages(report, sha256)
  assert.equal(verified.keyframes.length, 3)
  assert.ok(verified.keyframes.every((frame) => frame.imageValid && frame.imageError === null && frame.dataUri?.startsWith('data:image/jpeg;base64,')))
  assert.equal('imageValid' in report.keyframes[0], false)
})

test('required report fields, format, types and invalid UTF-8 are rejected', () => {
  for (const field of Object.keys(fixture())) {
    const source: Record<string, unknown> = fixture()
    delete source[field]
    assert.throws(() => parseTransferReport(encode(source)), field)
  }
  for (const [field, value] of [
    ['format', 'other.report'], ['version', 2], ['version', true], ['incident_id', ''],
    ['model', 5], ['summary', {}], ['observations', {}], ['limitations', [5]], ['warnings', [null]],
    ['digests', {}], ['digests', { 'clip.mp4': 'invalid' }], ['major_negligence_review', []],
  ] as const) {
    assert.throws(() => parseTransferReport(encode({ ...fixture(), [field]: value })), field)
  }
  assert.throws(() => parseTransferReport(Uint8Array.of(0xff)))
  assert.throws(() => parseTransferReport(encode(null)))
  assert.throws(() => parseTransferReport(new TextEncoder().encode('{bad')))
})

test('dates require a real calendar date, a valid time, and a timezone', () => {
  for (const value of ['invalid', '2026-02-30T10:00:00Z', '2026-02-29T10:00:00Z', '2026-13-01T10:00:00Z',
    '2026-10-04', '2026-10-04T10:00:00', '2026-10-04T24:00:00Z', '2026-10-04T10:00:00+24:00']) {
    for (const field of ['triggered_at', 'generated_at']) {
      assert.throws(() => parseTransferReport(encode({ ...fixture(), [field]: value })), value)
    }
  }
  assert.doesNotThrow(() => parseTransferReport(encode({ ...fixture(), triggered_at: '2024-02-29T23:59:59.999+09:00' })))
})

test('all report timestamps must be numeric, finite, and nonnegative', () => {
  for (const value of [-1, '2', true, null]) {
    assert.throws(() => parseTransferReport(encode({ ...fixture(), incident_timestamp: value })))
    assert.throws(() => parseTransferReport(encode({ ...fixture(), observations: [{ timestamp: value, description: 'x' }] })))
    const source = fixture()
    Object.assign(source.keyframes[0], { timestamp: value })
    assert.throws(() => parseTransferReport(encode(source)))
    source.keyframes[0].timestamp = 0
    source.major_negligence_review.signal = { status: 'observed', evidence: 'x', timestamp: value }
    if (value !== null) assert.throws(() => parseTransferReport(encode(source)))
  }
  // JSON accepts overflowing exponents as Infinity; these must not pass field validation.
  assert.throws(() => parseTransferReport(new TextEncoder().encode(JSON.stringify(fixture()).replace('"incident_timestamp":2', '"incident_timestamp":1e400'))))
})

test('keyframes require precisely one of each role, valid metadata, and string image data', () => {
  const base = fixture()
  for (const frames of [[], base.keyframes.slice(0, 2), [...base.keyframes, base.keyframes[0]],
    [base.keyframes[0], base.keyframes[0], base.keyframes[2]],
    [{ ...base.keyframes[0], role: 'unknown' }, ...base.keyframes.slice(1)],
    [{ ...base.keyframes[0], sha256: 'bad' }, ...base.keyframes.slice(1)],
    [{ ...base.keyframes[0], jpeg_base64: 42 }, ...base.keyframes.slice(1)],
  ]) assert.throws(() => parseTransferReport(encode({ ...base, keyframes: frames })))
})

test('missing or unknown review entries become unavailable and nonvisual conclusions are removed', () => {
  const source = fixture()
  delete source.major_negligence_review.center_line
  source.major_negligence_review.signal = { status: 'guilty', evidence: 'unsupported claim', timestamp: 1 }
  source.major_negligence_review.unknown = { status: 'observed', evidence: 'unknown', timestamp: 1 }
  for (const key of ['speeding', 'unlicensed', 'intoxication']) {
    source.major_negligence_review[key] = { status: 'observed', evidence: 'unsupported claim', timestamp: 1 }
  }
  const report = parseTransferReport(encode(source))
  assert.equal(Object.keys(report.major_negligence_review).length, 12)
  for (const key of ['signal', 'center_line', 'speeding', 'unlicensed', 'intoxication'] as const) {
    assert.equal(report.major_negligence_review[key].status, 'not_determinable')
    assert.equal(report.major_negligence_review[key].timestamp, null)
    assert.equal(report.major_negligence_review[key].evidence.includes('unsupported'), false)
  }
  source.major_negligence_review.school_zone = { status: 'observed', evidence: '어린이가 보임', timestamp: 1 }
  assert.equal(parseTransferReport(encode(source)).major_negligence_review.school_zone.status, 'not_determinable')
  source.major_negligence_review.school_zone.evidence = '노면 표시가 보임'
  assert.equal(parseTransferReport(encode(source)).major_negligence_review.school_zone.status, 'observed')
  for (const entry of [{}, { evidence: 'unknown', timestamp: 1 }, { status: null }, { status: { toString: 1 } }]) {
    const report = parseTransferReport(encode({ ...fixture(), major_negligence_review: { signal: entry } }))
    assert.equal(report.major_negligence_review.signal.status, 'not_determinable')
  }
})

test('invalid image bytes and digests damage only their own placeholders', async () => {
  const corrupt = ['', '%%%=', 'A===', '/9g', '/9h=', Buffer.from('not jpeg').toString('base64'),
    'A'.repeat(4 * Math.ceil(MAX_REPORT_IMAGE_BYTES / 3) + 4)]
  for (const data of corrupt) {
    const source = fixture()
    source.keyframes[0].jpeg_base64 = data
    const verified = await verifyReportImages(parseTransferReport(encode(source)), sha256)
    assert.equal(verified.keyframes[0].imageValid, false, data.slice(0, 12))
    assert.equal(verified.keyframes[0].dataUri, null)
    assert.equal(verified.keyframes[0].imageError, IMAGE_DAMAGED)
    assert.equal(verified.keyframes[1].imageValid, true)
    assert.equal(verified.keyframes[2].imageValid, true)
  }
  const source = fixture()
  source.keyframes[1].sha256 = '0'.repeat(64)
  const verified = await verifyReportImages(parseTransferReport(encode(source)), sha256)
  assert.equal(verified.keyframes[1].imageValid, false)
  const unavailableHash = await verifyReportImages(parseTransferReport(encode(fixture())), async () => { throw new Error('digest failed') })
  assert.ok(unavailableHash.keyframes.every((frame) => !frame.imageValid))
})

test('decoded image limit accepts 200000 bytes and rejects 200001 before hashing', async () => {
  for (const size of [MAX_REPORT_IMAGE_BYTES, MAX_REPORT_IMAGE_BYTES + 1]) {
    const bytes = Buffer.alloc(size)
    bytes[0] = 0xff
    bytes[1] = 0xd8
    const source = fixture()
    source.keyframes[0].jpeg_base64 = bytes.toString('base64')
    source.keyframes[0].sha256 = hash(bytes)
    let calls = 0
    const verified = await verifyReportImages(parseTransferReport(encode(source)), async (input) => { calls += 1; return hash(input) })
    assert.equal(verified.keyframes[0].imageValid, size === MAX_REPORT_IMAGE_BYTES)
    assert.equal(calls, size === MAX_REPORT_IMAGE_BYTES ? 3 : 2)
  }
})

test('relative times and closest frames account for clipped boundaries and deterministic ties', () => {
  assert.equal(relativeTimestamp(0, 2), '-2.0초')
  assert.equal(relativeTimestamp(2, 2), '0.0초')
  assert.equal(relativeTimestamp(4, 2), '+2.0초')
  assert.equal(relativeTimestamp(1.99, 2), '0.0초')
  const frames = parseTransferReport(encode(fixture())).keyframes
  assert.equal(nearestKeyframe(1, [...frames].reverse()), 'moment')
  assert.equal(nearestKeyframe(3, frames), 'moment')
  assert.equal(nearestKeyframe(-10, frames), 'before')
  assert.equal(nearestKeyframe(10, frames), 'after')
  const sparse = [{ role: 'before' as const, timestamp: 0 }, { role: 'moment' as const, timestamp: 20 }, { role: 'after' as const, timestamp: 4 }]
  assert.equal(nearestKeyframe(2, sparse), 'before')
  const boundary = [{ role: 'before' as const, timestamp: 0 }, { role: 'moment' as const, timestamp: 0 }, { role: 'after' as const, timestamp: 0.7 }]
  assert.equal(nearestKeyframe(0, boundary), 'moment')
})

test('native preview routing keeps malformed JSON shareable as its existing original file', () => {
  const model = previewForFile({ name: 'report.json', mediaType: `${REPORT_MEDIA_TYPE.toUpperCase()}; charset=utf-8`, payload: encode(fixture()) })
  assert.equal(model.kind, 'native-report')
  assert.deepEqual(previewForFile({ name: 'bad.json', mediaType: REPORT_MEDIA_TYPE, payload: encode({}) }), { kind: 'message', message: REPORT_OPEN_FAILED })
})

test('HTML export is offline, displays all evidence, and escapes hostile text throughout', async () => {
  const source = fixture()
  const attack = `<script>alert("x")</script><img src="https://example.com/x" onerror='attack()'>&`
  source.summary = attack
  source.incident_id = attack
  source.model = attack
  source.observations[0].description = attack
  source.limitations = [attack]
  source.warnings = [attack]
  source.major_negligence_review.signal = { status: 'observed', evidence: attack, timestamp: 2 }
  const html = renderReportHtml(await verifyReportImages(parseTransferReport(encode(source)), sha256))
  assert.equal((html.match(/<img /g) ?? []).length, 3)
  assert.equal((html.match(/<figure>/g) ?? []).length, 3)
  assert.match(html, /&lt;script&gt;alert\(&quot;x&quot;\)&lt;\/script&gt;/)
  assert.equal(html.includes('<script'), false)
  assert.equal(/\son\w+=/.test(html.replace(/&lt;[\s\S]*?&gt;/g, '')), false)
  assert.equal(/(?:src|href)=["']https?:/.test(html), false)
  assert.equal(html.includes('<a '), false)
  assert.match(html, /법적 판정이 아니라 관련 장면이 보였는지만 정리했습니다/)
  assert.match(html, /119 구급·소방/)
  assert.match(html, /112 경찰/)
  assert.match(html, /원본 클립 SHA-256/)
  assert.ok(html.includes(source.digests['clip.mp4']))
  assert.match(html, /\+2\.0초/)
  assert.equal((html.match(/class="status /g) ?? []).length, 12)
})

test('HTML omits damaged images while keeping their evidence and placeholder', async () => {
  const source = fixture()
  source.keyframes[1].sha256 = '0'.repeat(64)
  const report = await verifyReportImages(parseTransferReport(encode(source)), sha256)
  const html = renderReportHtml(report)
  assert.equal((html.match(/<img /g) ?? []).length, 2)
  assert.match(html, /이미지 손상/)
  assert.ok(html.includes('0'.repeat(64)))
  assert.equal((html.match(/<figure>/g) ?? []).length, 3)
})
