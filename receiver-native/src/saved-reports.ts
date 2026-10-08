import type { OpticalFile } from './unpack'
import { REPORT_MEDIA_TYPE, parseTransferReport, verifyReportImages, type ValidatedNativeReport } from './native-report.ts'
import { renderReportHtml } from './report-html.ts'

export type SavedReport = {
  name: string
  mediaType: string
  size: number
  triggeredAt?: string
  summary?: string
  thumbnailUri?: string
  unreadable?: boolean
}

export type ImageDigest = (bytes: Uint8Array) => Promise<string>

export function isNativeReportFile(file: { mediaType: string }): boolean {
  return file.mediaType.split(';', 1)[0].trim().toLowerCase() === REPORT_MEDIA_TYPE
}

/** Read each record independently so one damaged file never hides the others. */
export async function describeSavedReports(store: ReportStore, sha256: ImageDigest): Promise<SavedReport[]> {
  const rows = await Promise.all(store.list().map(async (row): Promise<SavedReport> => {
    if (row.unreadable || !isNativeReportFile(row)) return row
    try {
      const file = store.get(row.name)
      if (!file) return { ...row, unreadable: true }
      if (!isNativeReportFile(file)) return row
      const report = await verifyReportImages(parseTransferReport(file.payload), sha256)
      const moment = report.keyframes.find((frame) => frame.role === 'moment')
      return {
        ...row,
        triggeredAt: report.triggered_at,
        summary: report.summary.split(/\r?\n/, 1)[0],
        thumbnailUri: moment?.imageValid ? moment.dataUri ?? undefined : undefined,
      }
    } catch {
      return { ...row, unreadable: true }
    }
  }))
  return rows.sort((left, right) => {
    const leftTime = left.triggeredAt ? Date.parse(left.triggeredAt) : -Infinity
    const rightTime = right.triggeredAt ? Date.parse(right.triggeredAt) : -Infinity
    if (leftTime !== rightTime) return rightTime > leftTime ? 1 : -1
    return left.name.localeCompare(right.name)
  })
}

/** Keep the received bytes intact; conversion is only for the share cache. */
export async function prepareReportShare(
  file: OpticalFile,
  sha256: ImageDigest,
  verified?: ValidatedNativeReport,
): Promise<OpticalFile> {
  if (!isNativeReportFile(file)) return file
  let parsed
  try {
    parsed = parseTransferReport(file.payload)
  } catch {
    return file
  }
  const report = verified ?? await verifyReportImages(parsed, sha256)
  return {
    name: `dashpi-${report.incident_id}.html`,
    mediaType: 'text/html',
    payload: new TextEncoder().encode(renderReportHtml(report, 'print')),
  }
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
