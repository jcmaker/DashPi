import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const packageRoot = fileURLToPath(new URL('..', import.meta.url))
execFileSync(process.execPath, ['scripts/patch-webview-sandbox.mjs'], { cwd: packageRoot })
execFileSync(process.execPath, ['scripts/patch-webview-sandbox.mjs'], { cwd: packageRoot })

function source(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), 'utf8')
}
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

test('the report WebView turns on the native load block, which is not the CSP', () => {
  const props = verifiedHtmlWebViewProps('<p>report</p>')
  assert.equal(props.blockNonDocumentLoads, true)
  assert.match(source('../App.tsx'), /<WebView \{\.\.\.verifiedHtmlWebViewProps\(screen\.html\)\}/)
  assert.match(source('../package.json'), /patch-webview-sandbox\.mjs/)

  const client = source(
    '../node_modules/react-native-webview/android/src/main/java/com/reactnativecommunity/webview/RNCWebViewClient.java',
  )
  const view = source(
    '../node_modules/react-native-webview/android/src/main/java/com/reactnativecommunity/webview/RNCWebView.java',
  )
  const chrome = source(
    '../node_modules/react-native-webview/android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java',
  )
  const manager = source(
    '../node_modules/react-native-webview/android/src/newarch/com/reactnativecommunity/webview/RNCWebViewManager.java',
  )
  const spec = source('../node_modules/react-native-webview/src/RNCWebViewNativeComponent.ts')

  assert.match(spec, /blockNonDocumentLoads\?: WithDefault<boolean, false>/)
  assert.match(manager, /@ReactProp\(name = "blockNonDocumentLoads"\)/)
  assert.match(view, /getSettings\(\)\.setBlockNetworkLoads\(true\)/)
  assert.match(view, /setSuppressFileChooser\(enabled\)/)
  assert.match(client, /SHOULD_OVERRIDE_URL_LOADING_TIMEOUT = 250/)
  assert.match(client, /shouldInterceptRequest\(WebView view, WebResourceRequest request\)/)
  assert.match(client, /shouldInterceptRequest\(WebView view, String url\)/)
  assert.match(client, /"data"\.equalsIgnoreCase\(scheme\)/)
  assert.match(client, /"blank"\.equals\(rest\)/)
  assert.match(client, /new WebResourceResponse\(/)
  const intercept = client.slice(client.indexOf('shouldInterceptRequest(WebView view, WebResourceRequest request)'))
  assert.match(intercept, /if \(!mBlockNonDocumentLoads \|\| allowsVerifiedDocumentResource/)
  assert.doesNotMatch(intercept.slice(0, 500), /SHOULD_OVERRIDE_URL_LOADING_TIMEOUT/)

  const show = chrome.slice(chrome.indexOf('boolean onShowFileChooser'))
  const cancel = show.indexOf('filePathCallback.onReceiveValue(null)')
  const picker = show.indexOf('startPhotoPickerIntent')
  assert.ok(cancel > 0 && picker > cancel)
  assert.match(show, /return true;/)
  assert.match(chrome, /ACTION_IMAGE_CAPTURE|startPhotoPickerIntent/)
})
