import { Directory, File, Paths } from 'expo-file-system'
import { presentShareSheet } from 'dashpi-share'
import { isShareCacheName, randomShareId, SHARE_CACHE_DIRECTORY, shareReportFile, type CacheFile } from './share-report'

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
    present: (file, mediaType) => presentShareSheet(file.uri, mediaType),
  })
}
