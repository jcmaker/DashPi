import assert from 'node:assert/strict'
import test from 'node:test'
import {
  PLAYBACK_UNAVAILABLE,
  PREVIEW_OPEN_FAILED,
  previewForFile,
  unsupportedPreviewMessage,
  videoStorageName,
} from '../src/preview-model.ts'

function reportHtml(videoSource: string, image = Buffer.from('before').toString('base64')): string {
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DashPi 사고 분석 리포트</title><style>
@media print{body{background:white}.screen-only{display:none!important}}
</style></head><body><main>
<header><h1>사고 분석 리포트</h1></header>
<section class="video screen-only" data-section="video"><video controls preload="metadata" src="${videoSource}"></video></section>
<section data-section="summary"><h2>AI 핵심 요약</h2><p>사고 요약</p></section>
<section class="keyframes"><figure><img src="data:image/jpeg;base64,${image}" alt="사고 전"><figcaption>사고 전</figcaption></figure></section>
<nav class="screen-only"><button type="button" onclick="downloadReport()">Download HTML</button><button type="button" onclick="window.print()">Save as PDF</button></nav>
</main><script>
function downloadReport(){const blob=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{type:'text/html'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='report.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),0)}
</script></body></html>`
}

test('a report keeps its pictures, lifts out the data video, and drops dead save controls', () => {
  const video = Buffer.from('video-bytes')
  const image = Buffer.from('image-bytes')
  const model = previewForFile({
    name: 'report.html',
    mediaType: 'text/html',
    payload: new TextEncoder().encode(reportHtml(`data:video/mp4;base64,${video.toString('base64')}`, image.toString('base64'))),
  })

  assert.equal(model.kind, 'html')
  if (model.kind !== 'html') return
  assert.equal(model.playbackNotice, null)
  assert.equal(model.videos.length, 1)
  assert.equal(model.videos[0].mediaType, 'video/mp4')
  assert.equal(model.videos[0].filename, 'embedded-0.mp4')
  assert.deepEqual(Buffer.from(model.videos[0].bytes), video)
  assert.match(model.html, /data:image\/jpeg;base64,/)
  assert.match(model.html, /사고 분석 리포트/)
  assert.match(model.html, /@media print/)
  assert.equal(model.html.includes('data:video/'), false)
  assert.equal(model.html.includes('<video'), false)
  assert.equal(model.html.includes('data-section="video"'), false)
  assert.match(model.html, /data-section="summary"/)
  assert.equal(model.html.includes('<button'), false)
  assert.equal(model.html.includes('Download HTML'), false)
  assert.equal(model.html.includes('Save as PDF'), false)
  assert.equal(model.html.includes('downloadReport'), false)
  assert.equal(model.html.includes('createObjectURL'), false)
  assert.equal(model.html.includes('window.print'), false)
})

test('a video source element is extracted and a remote video is not fetched', () => {
  const clip = Buffer.from('webm-bytes')
  const html = [
    '<img src="data:image/jpeg;base64,QQ==" alt="사고 순간">',
    `<video controls><source src="data:video/webm;base64,${clip.toString('base64')}" type="video/webm"></video>`,
    '<video src="https://example.com/clip.mp4"></video>',
    '<button type="button" onclick="window.print()">Save as PDF</button>',
  ].join('')
  const model = previewForFile({
    name: 'report.html',
    mediaType: 'text/html; charset=utf-8',
    payload: new TextEncoder().encode(html),
  })

  assert.equal(model.kind, 'html')
  if (model.kind !== 'html') return
  assert.equal(model.playbackNotice, PLAYBACK_UNAVAILABLE)
  assert.equal(model.videos.length, 1)
  assert.equal(model.videos[0].filename, 'embedded-0.webm')
  assert.deepEqual(Buffer.from(model.videos[0].bytes), clip)
  assert.match(model.html, /data:image\/jpeg/)
  assert.equal(model.html.includes('example.com'), false)
  assert.equal(model.html.includes('<video'), false)
  assert.equal(model.html.includes('Save as PDF'), false)
})

test('video files use a native player and other types explain themselves', () => {
  assert.deepEqual(previewForFile({ name: 'clip.mp4', mediaType: 'Video/MP4', payload: Uint8Array.of(1) }), {
    kind: 'video',
    filename: 'clip.mp4',
  })
  assert.equal(videoStorageName('take', 'video/quicktime'), 'take.mov')
  assert.equal(videoStorageName('../clip.mp4', 'video/mp4').includes('/'), false)
  const notes = previewForFile({ name: 'notes.pdf', mediaType: 'application/pdf', payload: Uint8Array.of(1) })
  assert.deepEqual(notes, { kind: 'message', message: unsupportedPreviewMessage('notes.pdf') })
})

test('html that cannot be read explains the failure instead of a blank document', () => {
  const model = previewForFile({ name: 'report.html', mediaType: 'text/html', payload: Uint8Array.of(0xff) })
  assert.deepEqual(model, { kind: 'message', message: PREVIEW_OPEN_FAILED })
})
