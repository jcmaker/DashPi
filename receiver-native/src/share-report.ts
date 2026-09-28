export const SHARE_CACHE_DIRECTORY = 'dashpi-share'

const SHARE_ID = /^[0-9a-f]{32}$/
const SHARE_EXTENSION = /^\.[a-z0-9]{1,8}$/
const SHARE_CACHE_NAME = /^[0-9a-f]{32}(?:\.[a-z0-9]{1,8})?$/

export type CacheFile = {
  name: string
  uri: string
  readonly exists: boolean
  write: (payload: Uint8Array) => void
  bytes: () => Uint8Array
  delete: () => void
}

const inFlight = new Set<string>()

export function isShareCacheName(name: string): boolean {
  return SHARE_CACHE_NAME.test(name)
}

export function shareCacheName(reportName: string, randomId: string): string {
  if (!SHARE_ID.test(randomId)) {
    throw new Error('share cache id is not a random 128-bit hex string')
  }
  const dot = reportName.lastIndexOf('.')
  const rawExtension = dot > 0 ? reportName.slice(dot).toLowerCase() : ''
  const extension = SHARE_EXTENSION.test(rawExtension) ? rawExtension : ''
  const name = `${randomId}${extension}`
  if (name === reportName || reportName.includes(randomId)) {
    throw new Error('share cache name must not be the report name')
  }
  return name
}

export function randomShareId(fill: (bytes: Uint8Array) => void = (bytes) => crypto.getRandomValues(bytes)): string {
  const bytes = new Uint8Array(16)
  fill(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function shareFileStillNeeded(name: string): boolean {
  return inFlight.has(name)
}

export type SharePresentation =
  | { outcome: 'dismissed' }
  | { outcome: 'sent'; finished: Promise<void> }

export async function shareReportFile(input: {
  reportName: string
  mediaType: string
  payload: Uint8Array
  randomId: string
  openCacheFile: (name: string) => CacheFile
  present: (file: CacheFile, mediaType: string) => Promise<SharePresentation>
  stillNeeded?: (file: CacheFile) => boolean
}): Promise<void> {
  const cacheName = shareCacheName(input.reportName, input.randomId)
  if (inFlight.has(cacheName)) throw new Error('share file is still needed')
  inFlight.add(cacheName)
  let file: CacheFile | undefined
  try {
    file = input.openCacheFile(cacheName)
    if (file.name !== cacheName) throw new Error('share cache file name was rewritten')
    file.write(Uint8Array.from(input.payload))
    const presentation = await input.present(file, input.mediaType)
    if (presentation.outcome === 'sent') await presentation.finished
  } finally {
    inFlight.delete(cacheName)
    if (file && !shareFileStillNeeded(file.name) && !input.stillNeeded?.(file) && file.exists) {
      file.delete()
    }
  }
}
