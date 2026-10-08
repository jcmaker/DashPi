import { Directory, File, Paths } from 'expo-file-system'
import { presentShareSheet } from 'dashpi-share'
import * as Crypto from 'expo-crypto'
import { prepareReportShare } from './saved-reports'
import type { ValidatedNativeReport } from './native-report'
import {
  isShareCacheName,
  randomShareId,
  SHARE_CACHE_DIRECTORY,
  shareReportFile,
  type CacheFile,
  type SharePresentation,
} from './share-report'

function openDashpiShareFile(name: string): CacheFile {
  if (!isShareCacheName(name)) throw new Error('refusing to open a predictable share cache name')
  const directory = new Directory(Paths.cache, SHARE_CACHE_DIRECTORY)
  if (!directory.exists) directory.create({ intermediates: true, idempotent: true })
  const stored = new File(directory, name)
  return {
    name,
    get uri() {
      return stored.uri
    },
    get exists() {
      return stored.exists
    },
    write(payload: Uint8Array) {
      if (stored.exists) stored.delete()
      stored.create()
      stored.write(payload)
    },
    bytes() {
      return stored.bytesSync()
    },
    delete() {
      if (stored.exists) stored.delete()
    },
  }
}

export function shareReceivedReport(report: {
  name: string
  mediaType: string
  payload: Uint8Array
}): Promise<void> {
  return shareReportFile({
    reportName: report.name,
    mediaType: report.mediaType,
    payload: report.payload,
    randomId: randomShareId(),
    openCacheFile: openDashpiShareFile,
    present: (file, mediaType) => presentUntilCleanup(file.uri, mediaType),
  })
}

async function presentUntilCleanup(uri: string, mediaType: string): Promise<SharePresentation> {
  // shareAsync stays pending while the chosen activity is open. It resolves when that
  // activity finishes, or immediately if the sheet is dismissed with no target.
  await presentShareSheet(uri, mediaType)
  return { outcome: 'dismissed' }
}

export type ShareOutcome =
  | { status: 'shared' }
  | { status: 'busy' }
  | { status: 'failed'; reason: string }

export function applyShareOutcome<T extends { error?: string }>(screen: T, outcome: ShareOutcome): T {
  if (outcome.status === 'failed') return { ...screen, error: outcome.reason }
  if (outcome.status === 'shared') return { ...screen, error: undefined }
  return screen
}

let shareInProgress = false

export async function shareReport(file: {
  name: string
  mediaType: string
  payload: Uint8Array
}, verified?: ValidatedNativeReport): Promise<ShareOutcome> {
  if (shareInProgress) return { status: 'busy' }
  shareInProgress = true
  try {
    await shareReceivedReport(await prepareReportShare(file, digestReportImage, verified))
    return { status: 'shared' }
  } catch (error) {
    const reason = error instanceof Error && error.message.trim()
      ? error.message
      : '공유에 실패했습니다. 앱에 저장된 리포트는 그대로 있습니다.'
    return { status: 'failed', reason }
  } finally {
    shareInProgress = false
  }
}

export async function digestReportImage(payload: Uint8Array): Promise<string> {
  const input = new Uint8Array(payload.byteLength)
  input.set(payload)
  const digest = new Uint8Array(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, input))
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, '0')).join('')
}
