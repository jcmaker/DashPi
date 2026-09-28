// react-native-webview 13.16 calls Linking.openURL for any navigation that fails
// originWhitelist, and it does that before onShouldStartLoadWithRequest.
// ['*'] is what keeps a refused URL inside that callback. A tighter list hands
// the URL to the system browser, so the whitelist is not the sandbox.

export const verifiedHtmlOriginWhitelist = ['*']

export const verifiedHtmlContentSecurityPolicy = [
  "default-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
  "script-src 'none'",
  "style-src 'unsafe-inline'",
  'img-src data:',
  'media-src data:',
].join('; ')

const cspMeta = `<meta http-equiv="Content-Security-Policy" content="${verifiedHtmlContentSecurityPolicy}">`

export function sandboxVerifiedHtml(html: string): string {
  const head = /<head\b[^>]*>/i.exec(html)
  if (!head) return `<head>${cspMeta}</head>${html}`
  const at = head.index + head[0].length
  return html.slice(0, at) + cspMeta + html.slice(at)
}

// iOS asks onShouldStartLoadWithRequest for the initial loadHTMLString, whose
// base URL is about:blank. Android does not ask for that first load. Every
// other URL is a navigation and is refused.
export function allowVerifiedHtmlLoad(url: string): boolean {
  return url === 'about:blank' || url === 'about:blank/'
}

export function verifiedHtmlWebViewProps(html: string) {
  return {
    originWhitelist: verifiedHtmlOriginWhitelist,
    javaScriptEnabled: false as const,
    setSupportMultipleWindows: false as const,
    mediaCapturePermissionGrantType: 'deny' as const,
    source: { html: sandboxVerifiedHtml(html) },
    onShouldStartLoadWithRequest: (request: { url: string }) => allowVerifiedHtmlLoad(request.url),
  }
}

// Same origin check as react-native-webview's createOnShouldStartLoadWithRequest.
// about:blank is always compiled in. A miss is what the library passes to Linking.openURL.
export function systemBrowserUrl(originWhitelist: readonly string[], url: string): string | null {
  return passesOriginWhitelist(originWhitelist, url) ? null : url
}

function passesOriginWhitelist(originWhitelist: readonly string[], url: string): boolean {
  const origin = /^[A-Za-z][A-Za-z0-9+\-.]+:(\/\/)?[^/]*/.exec(url)?.[0] ?? ''
  return ['about:blank', ...originWhitelist].some((entry) => originPattern(entry).test(origin))
}

function originPattern(entry: string): RegExp {
  // escape-string-regexp, then react-native-webview turns \* into .*
  const escaped = entry
    .replace(/[|\\{}()[\]^$+*?.]/g, '\\$&')
    .replace(/-/g, '\\x2d')
    .replace(/\\\*/g, '.*')
  return new RegExp(`^${escaped}`)
}
