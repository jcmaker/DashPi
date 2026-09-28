import assert from 'node:assert/strict'
import test from 'node:test'
import {
  allowVerifiedHtmlLoad,
  sandboxVerifiedHtml,
  systemBrowserUrl,
  verifiedHtmlContentSecurityPolicy,
  verifiedHtmlOriginWhitelist,
  verifiedHtmlWebViewProps,
} from '../src/webview-policy.ts'

const remoteUrls = [
  'https://evil.example/script.js',
  'http://evil.example/frame.html',
  'javascript:alert(1)',
  'intent://evil.example#Intent;scheme=https;end',
  'file:///sdcard/secret',
  'data:text/html,<script>navigator.mediaDevices.getUserMedia({video:true})</script>',
]

test('verified HTML WebView keeps JavaScript off and refuses new windows', () => {
  const props = verifiedHtmlWebViewProps('<p>report</p>')
  assert.equal(props.javaScriptEnabled, false)
  assert.equal(props.setSupportMultipleWindows, false)
  assert.equal(props.mediaCapturePermissionGrantType, 'deny')
  assert.deepEqual(props.originWhitelist, ['*'])
  assert.deepEqual(verifiedHtmlOriginWhitelist, ['*'])
})

test('refuses navigations and does not hand the blocked URL to the system browser', () => {
  const props = verifiedHtmlWebViewProps('<p>report</p>')
  for (const url of remoteUrls) {
    assert.equal(props.onShouldStartLoadWithRequest({ url }), false, url)
    assert.equal(allowVerifiedHtmlLoad(url), false, url)
    assert.equal(systemBrowserUrl(props.originWhitelist, url), null, url)
  }
})

test('allows only the local document so the initial HTML can render', () => {
  const props = verifiedHtmlWebViewProps('<p>report</p>')
  assert.equal(props.onShouldStartLoadWithRequest({ url: 'about:blank' }), true)
  assert.equal(props.onShouldStartLoadWithRequest({ url: 'about:blank/' }), true)
})

test('a tighter origin whitelist would open the blocked URL in the system browser', () => {
  for (const url of remoteUrls) {
    assert.equal(systemBrowserUrl([], url), url)
    assert.equal(systemBrowserUrl(['about:blank'], url), url)
  }
  assert.equal(systemBrowserUrl(['https://*'], 'https://evil.example/a'), null)
  assert.equal(systemBrowserUrl(['https://*'], 'http://evil.example/a'), 'http://evil.example/a')
})

test('display HTML keeps inline CSS and data images and video, and blocks network sources', () => {
  const report = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>body{margin:0;color:#fff}</style></head><body>
<video controls src="data:video/mp4;base64,AAAA"></video>
<img src="data:image/jpeg;base64,BBBB" alt="사고 순간">
<script>function downloadReport(){}</script>
</body></html>`
  const displayed = sandboxVerifiedHtml(report)
  assert.notEqual(displayed, report)
  assert.match(displayed, /<style>body\{margin:0;color:#fff\}<\/style>/)
  assert.match(displayed, /src="data:video\/mp4;base64,AAAA"/)
  assert.match(displayed, /src="data:image\/jpeg;base64,BBBB"/)
  assert.match(displayed, /http-equiv="Content-Security-Policy"/)
  assert.match(displayed, /script-src 'none'/)
  assert.doesNotMatch(verifiedHtmlContentSecurityPolicy, /https?:/)
  assert.doesNotMatch(verifiedHtmlContentSecurityPolicy, /script-src 'unsafe-inline'/)
  assert.match(verifiedHtmlContentSecurityPolicy, /style-src 'unsafe-inline'/)
  assert.match(verifiedHtmlContentSecurityPolicy, /img-src data:/)
  assert.match(verifiedHtmlContentSecurityPolicy, /media-src data:/)
  assert.match(verifiedHtmlContentSecurityPolicy, /frame-src 'none'/)
  const props = verifiedHtmlWebViewProps(report)
  assert.equal(props.source.html, displayed)
})

test('inserts the content security policy when the report has no head', () => {
  const displayed = sandboxVerifiedHtml('<img src="data:image/jpeg;base64,QQ">')
  assert.match(displayed, /^<head><meta http-equiv="Content-Security-Policy"/)
  assert.match(displayed, /src="data:image\/jpeg;base64,QQ"/)
})
