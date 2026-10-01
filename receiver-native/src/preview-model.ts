export const PLAYBACK_UNAVAILABLE = '이 영상은 재생할 수 없습니다. 공유하거나 파일로 저장하세요.'
export const PREVIEW_OPEN_FAILED = '미리보기를 열지 못했습니다. 공유해서 저장할 수 있습니다.'
export const PREVIEW_PREPARING = '미리보기를 준비하고 있습니다.'
export const DOCUMENT_OPENING = '문서를 열고 있습니다.'

const VIDEO_EXTENSIONS: Record<string, string> = {
  'video/mp4': 'mp4',
  'video/quicktime': 'mov',
  'video/webm': 'webm',
  'video/3gpp': '3gp',
  'video/3gpp2': '3g2',
  'video/x-m4v': 'm4v',
  'video/ogg': 'ogv',
  'video/x-matroska': 'mkv',
}

export type EmbeddedVideo = {
  mediaType: string
  filename: string
  bytes: Uint8Array
}

export type PreviewModel =
  | { kind: 'html'; html: string; videos: EmbeddedVideo[]; playbackNotice: string | null }
  | { kind: 'video'; filename: string }
  | { kind: 'message'; message: string }

export type PreviewFile = {
  name: string
  mediaType: string
  payload: Uint8Array
}

function baseMediaType(mediaType: string): string {
  return mediaType.split(';', 1)[0].trim().toLowerCase()
}

export function videoStorageName(name: string, mediaType: string): string {
  const extension = VIDEO_EXTENSIONS[baseMediaType(mediaType)] ?? 'mp4'
  const stem = name.replace(/[^A-Za-z0-9._-]/g, '').replace(/\.[A-Za-z0-9]+$/, '') || 'clip'
  return `${stem}.${extension}`
}

export function unsupportedPreviewMessage(name: string): string {
  return `${name} 파일은 이 앱에서 미리 볼 수 없습니다. 공유하거나 파일로 저장하세요.`
}

function decodeUtf8(payload: Uint8Array): string | null {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(payload)
  } catch {
    return null
  }
}

function decodeBase64(value: string): Uint8Array {
  const cleaned = value.replace(/\s/g, '')
  if (!cleaned || cleaned.length % 4 === 1) throw new Error('bad base64')
  const binary = atob(cleaned)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return bytes
}

function stripSaveControls(html: string): string {
  const withoutButtons = html.replace(/<button\b[^>]*>[\s\S]*?<\/button>/gi, (button) => {
    const dead =
      /downloadReport\s*\(/.test(button) ||
      /window\.print\s*\(/.test(button) ||
      />\s*Download HTML\s*</i.test(button) ||
      />\s*Save as PDF\s*</i.test(button)
    return dead ? '' : button
  })
  const withoutBlobScript = withoutButtons.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (script) => {
    if (script.includes('downloadReport') || script.includes('createObjectURL')) return ''
    return script
  })
  return withoutBlobScript.replace(/<nav\b[^>]*\bscreen-only\b[^>]*>\s*<\/nav>/gi, '')
}

function dataVideo(fragment: string): { mediaType: string; bytes: Uint8Array } | null {
  const source = fragment.match(/\bsrc\s*=\s*["']([^"']+)["']/i)?.[1] ?? ''
  const match = source.match(/^data:(video\/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)$/i)
  if (!match) return null
  try {
    const bytes = decodeBase64(match[2])
    if (bytes.length === 0) return null
    return { mediaType: match[1].toLowerCase(), bytes }
  } catch {
    return null
  }
}

function replaceVideoElements(html: string, replacer: (fragment: string, index: number) => string): string {
  const lower = html.toLowerCase()
  let result = ''
  let cursor = 0
  let index = 0
  while (cursor < html.length) {
    const start = lower.indexOf('<video', cursor)
    if (start < 0) {
      result += html.slice(cursor)
      break
    }
    result += html.slice(cursor, start)
    const openEnd = html.indexOf('>', start)
    if (openEnd < 0) {
      result += replacer(html.slice(start), index)
      break
    }
    const selfClosing = /\/\s*>$/.test(html.slice(start, openEnd + 1))
    if (selfClosing) {
      result += replacer(html.slice(start, openEnd + 1), index)
      index += 1
      cursor = openEnd + 1
      continue
    }
    const close = lower.indexOf('</video>', openEnd)
    if (close < 0) {
      result += replacer(html.slice(start), index)
      break
    }
    const end = close + '</video>'.length
    result += replacer(html.slice(start, end), index)
    index += 1
    cursor = end
  }
  return result
}

function prepareHtml(html: string): { html: string; videos: EmbeddedVideo[]; playbackNotice: string | null } {
  let playbackNotice: string | null = null
  const videos: EmbeddedVideo[] = []
  const document = replaceVideoElements(stripSaveControls(html), (fragment, index) => {
    const extracted = dataVideo(fragment)
    if (!extracted) {
      playbackNotice = PLAYBACK_UNAVAILABLE
      return ''
    }
    const extension = VIDEO_EXTENSIONS[extracted.mediaType] ?? 'mp4'
    videos.push({
      mediaType: extracted.mediaType,
      filename: `embedded-${index}.${extension}`,
      bytes: extracted.bytes,
    })
    return ''
  }).replace(
    /<section\b(?=[^>]*\bscreen-only\b)(?=[^>]*\bdata-section\s*=\s*["']video["'])[^>]*>\s*<\/section>/gi,
    '',
  )
  return { html: document, videos, playbackNotice }
}

export function previewForFile(file: PreviewFile): PreviewModel {
  const mediaType = baseMediaType(file.mediaType)
  if (mediaType === 'text/html') {
    const html = decodeUtf8(file.payload)
    if (html === null || !html.trim()) return { kind: 'message', message: PREVIEW_OPEN_FAILED }
    return { kind: 'html', ...prepareHtml(html) }
  }
  if (mediaType.startsWith('video/')) {
    return { kind: 'video', filename: videoStorageName(file.name, mediaType) }
  }
  return { kind: 'message', message: unsupportedPreviewMessage(file.name) }
}
