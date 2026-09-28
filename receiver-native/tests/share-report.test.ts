import assert from 'node:assert/strict'
import test from 'node:test'
import { applyShareOutcome, createShareAttempt, type CacheFile, type ShareDialogOptions } from '../src/share-report.ts'

const htmlReport = {
  name: 'report.html',
  mediaType: 'text/html',
  payload: new Uint8Array([60, 112, 62]),
}

function verifiedScreen(error?: string) {
  return {
    phase: 'verified' as const,
    recovered: 2,
    total: 2,
    file: htmlReport,
    html: '<p>ok</p>',
    error,
  }
}

function cacheFile(uri: string): CacheFile & { calls: string[]; bytes: Uint8Array | null } {
  const calls: string[] = []
  let bytes: Uint8Array | null = null
  return {
    calls,
    get bytes() {
      return bytes
    },
    get exists() {
      return bytes !== null
    },
    uri,
    delete() {
      calls.push('delete')
      bytes = null
    },
    create() {
      calls.push('create')
      bytes = new Uint8Array()
    },
    write(content: Uint8Array) {
      calls.push('write')
      bytes = content
    },
  }
}

test('writes the report into the cache and opens one share sheet', async () => {
  const stored = cacheFile('file:///cache/report.html')
  const opened: string[] = []
  let options: ShareDialogOptions | undefined
  const attempt = createShareAttempt({
    open: (name) => {
      opened.push(name)
      return stored
    },
    shareAsync: async (_uri, dialog) => {
      options = dialog
    },
  })

  assert.deepEqual(await attempt(htmlReport), { status: 'shared' })
  assert.deepEqual(opened, ['report.html'])
  assert.deepEqual(stored.calls, ['create', 'write'])
  assert.equal(stored.bytes, htmlReport.payload)
  assert.deepEqual(options, {
    mimeType: 'text/html',
    dialogTitle: '리포트 저장',
    UTI: 'public.html',
  })
})

test('uses a generic data type for non-html reports', async () => {
  const stored = cacheFile('file:///cache/clip.bin')
  let options: ShareDialogOptions | undefined
  const attempt = createShareAttempt({
    open: () => stored,
    shareAsync: async (_uri, dialog) => {
      options = dialog
    },
  })

  await attempt({ name: 'clip.bin', mediaType: 'application/octet-stream', payload: new Uint8Array([1]) })
  assert.equal(options?.UTI, 'public.data')
  assert.equal(options?.mimeType, 'application/octet-stream')
})

test('keeps the verified report on screen when create or write fails', async () => {
  const reasons = ['ENOSPC: no space left on device', 'unable to create file']
  for (const reason of reasons) {
    let shared = 0
    const attempt = createShareAttempt({
      open: () => ({
        exists: false,
        uri: 'file:///cache/report.html',
        delete() {},
        create() {
          if (reason.startsWith('unable')) throw new Error(reason)
        },
        write() {
          throw new Error(reason)
        },
      }),
      shareAsync: async () => {
        shared += 1
      },
    })

    const outcome = await attempt(htmlReport)
    const screen = applyShareOutcome(verifiedScreen(), outcome)
    assert.deepEqual(outcome, { status: 'failed', reason })
    assert.equal(shared, 0)
    assert.equal(screen.phase, 'verified')
    assert.equal(screen.file, htmlReport)
    assert.equal(screen.html, '<p>ok</p>')
    assert.equal(screen.error, reason)
  }
})

test('keeps the verified report on screen when the share sheet fails', async () => {
  const attempt = createShareAttempt({
    open: () => cacheFile('file:///cache/report.html'),
    shareAsync: async () => {
      throw new Error('Sharing is not available')
    },
  })

  const outcome = await attempt(htmlReport)
  const screen = applyShareOutcome(verifiedScreen(), outcome)
  assert.equal(screen.phase, 'verified')
  assert.equal(screen.error, 'Sharing is not available')
})

test('still shows a reason when the failure is not an Error', async () => {
  const attempt = createShareAttempt({
    open: () => cacheFile('file:///cache/report.html'),
    shareAsync: async () => {
      throw 'disk full'
    },
  })
  assert.deepEqual(await attempt(htmlReport), { status: 'failed', reason: 'disk full' })

  const blank = createShareAttempt({
    open: () => {
      throw 0
    },
    shareAsync: async () => {},
  })
  assert.deepEqual(await blank(htmlReport), { status: 'failed', reason: '리포트를 공유하지 못했습니다.' })
})

test('a second tap while the sheet is open does not rewrite the cache file or open another sheet', async () => {
  const stored = cacheFile('file:///cache/report.html')
  const pending: Array<() => void> = []
  const shared: string[] = []
  let opens = 0
  const attempt = createShareAttempt({
    open: () => {
      opens += 1
      return stored
    },
    shareAsync: (uri) => {
      shared.push(uri)
      return new Promise((resolve) => {
        pending.push(resolve)
      })
    },
  })

  const first = attempt(htmlReport)
  const written = stored.bytes
  const second = await attempt(htmlReport)
  const duringSheet = applyShareOutcome(verifiedScreen('이전 실패'), second)

  assert.deepEqual(second, { status: 'busy' })
  assert.equal(duringSheet.phase, 'verified')
  assert.equal(duringSheet.error, '이전 실패')
  assert.equal(opens, 1)
  assert.deepEqual(shared, ['file:///cache/report.html'])
  assert.equal(stored.bytes, written)
  assert.deepEqual(stored.calls, ['create', 'write'])

  pending[0]()
  const finished = applyShareOutcome(duringSheet, await first)
  assert.equal(finished.phase, 'verified')
  assert.equal(finished.error, undefined)
  assert.equal(stored.bytes, htmlReport.payload)

  const again = attempt(htmlReport)
  assert.equal(shared.length, 2)
  assert.deepEqual(stored.calls, ['create', 'write', 'delete', 'create', 'write'])
  assert.equal(stored.bytes, htmlReport.payload)
  pending[1]()
  assert.deepEqual(await again, { status: 'shared' })
})

test('a failed attempt can be retried', async () => {
  let writes = 0
  const attempt = createShareAttempt({
    open: () => cacheFile('file:///cache/report.html'),
    shareAsync: async () => {
      writes += 1
      if (writes === 1) throw new Error('ENOSPC: no space left on device')
    },
  })

  assert.deepEqual(await attempt(htmlReport), {
    status: 'failed',
    reason: 'ENOSPC: no space left on device',
  })
  assert.deepEqual(await attempt(htmlReport), { status: 'shared' })
})
