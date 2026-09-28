import type { OpticalFile } from './unpack'

export type SavedReport = {
  name: string
  mediaType: string
  size: number
}

export type ReportStore = {
  put(name: string, mediaType: string, payload: Uint8Array): void
  list(): SavedReport[]
  get(name: string): OpticalFile | undefined
  remove(name: string): void
  uri(name: string): string | undefined
}

export class ReportSaveError extends Error {
  override readonly name = 'ReportSaveError'

  constructor(cause?: unknown) {
    super('report save failed', cause === undefined ? undefined : { cause })
  }
}

export function isSafeReportName(name: string): boolean {
  return (
    name.length > 0 &&
    name !== '.' &&
    name !== '..' &&
    !name.includes('/') &&
    !name.includes('\\') &&
    !name.includes('\0')
  )
}

export async function saveVerifiedReport(
  bytes: Uint8Array,
  unpack: (data: Uint8Array) => Promise<OpticalFile>,
  store: ReportStore,
): Promise<OpticalFile> {
  const file = await unpack(bytes)
  if (!isSafeReportName(file.name)) throw new Error('invalid container metadata')
  const payload = Uint8Array.from(file.payload)
  try {
    store.put(file.name, file.mediaType, payload)
  } catch (cause) {
    if (cause instanceof ReportSaveError) throw cause
    throw new ReportSaveError(cause)
  }
  return { name: file.name, mediaType: file.mediaType, payload }
}

export async function shareSavedReport(
  name: string,
  store: ReportStore,
  share: (uri: string, mediaType: string) => Promise<void>,
): Promise<void> {
  const saved = store.get(name)
  const uri = store.uri(name)
  if (!saved || !uri) throw new Error('saved report missing')
  await share(uri, saved.mediaType)
}
