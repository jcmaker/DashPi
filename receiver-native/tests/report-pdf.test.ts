import assert from 'node:assert/strict'
import test from 'node:test'
import { shareReportPdf } from '../src/report-pdf.ts'
import type { OpticalFile } from '../src/unpack.ts'

const html: OpticalFile = {
  name: 'dashpi-incident.html', mediaType: 'text/html',
  payload: new TextEncoder().encode('<!doctype html><html><body>검증된 사진과 분석</body></html>'),
}
const pdfBytes = new TextEncoder().encode('%PDF-1.7\nreport')

test('PDF conversion shares PDF bytes and retains the temporary file until sharing finishes', async () => {
  let removed = false
  const original = Uint8Array.from(html.payload)
  await shareReportPdf(html, {
    print: async (source) => {
      assert.equal(source, new TextDecoder().decode(html.payload))
      return { uri: 'file:///cache/print.pdf', numberOfPages: 3 }
    },
    read: async () => pdfBytes,
    share: async (file) => {
      assert.equal(removed, false)
      assert.equal(file.name, 'dashpi-incident.pdf')
      assert.equal(file.mediaType, 'application/pdf')
      assert.deepEqual(file.payload, pdfBytes)
    },
    remove: (uri) => { assert.equal(uri, 'file:///cache/print.pdf'); removed = true },
  })
  assert.equal(removed, true)
  assert.deepEqual(html.payload, original)
})

test('failed PDF reads, invalid output, and failed sharing clean up without changing the original', async () => {
  for (const failure of ['read', 'empty', 'header', 'share']) {
    let removed = false
    let shared = false
    const original = Uint8Array.from(html.payload)
    await assert.rejects(shareReportPdf(html, {
      print: async () => ({ uri: 'file:///cache/print.pdf', numberOfPages: failure === 'empty' ? 0 : 1 }),
      read: async () => {
        if (failure === 'read') throw new Error('read failed')
        return failure === 'header' ? html.payload : pdfBytes
      },
      share: async () => { shared = true; throw new Error('share failed') },
      remove: () => { removed = true },
    }))
    assert.equal(removed, true, failure)
    assert.equal(shared, failure === 'share', failure)
    assert.deepEqual(html.payload, original)
  }
})

test('renderer failures never present an HTML file as a PDF', async () => {
  await assert.rejects(shareReportPdf(html, {
    print: async () => { throw new Error('render failed') },
    read: async () => { assert.fail('must not read') },
    share: async () => { assert.fail('must not share') },
    remove: () => { assert.fail('no generated file to remove') },
  }), /render failed/)
})
