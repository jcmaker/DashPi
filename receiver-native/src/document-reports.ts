import { Directory, File, Paths } from 'expo-file-system'
import { isSafeReportName, type ReportStore, type SavedReport } from './saved-reports'
import type { OpticalFile } from './unpack'

const ROOT = 'dashpi-reports'

function directory(kind: 'files' | 'types'): Directory {
  return new Directory(Paths.document, ROOT, kind)
}

function ensureDirectory(kind: 'files' | 'types'): Directory {
  const folder = directory(kind)
  if (!folder.exists) folder.create({ intermediates: true, idempotent: true })
  return folder
}

function reportFile(name: string): File {
  return new File(directory('files'), name)
}

function typeFile(name: string): File {
  return new File(directory('types'), name)
}

function refuseUnsafe(name: string): void {
  if (!isSafeReportName(name)) throw new Error('invalid container metadata')
}

export function documentReportStore(): ReportStore {
  return {
    put(name, mediaType, payload) {
      refuseUnsafe(name)
      const file = new File(ensureDirectory('files'), name)
      const media = new File(ensureDirectory('types'), name)
      let created = false
      try {
        file.create({ overwrite: true })
        created = true
        file.write(payload)
        media.create({ overwrite: true })
        media.write(mediaType)
      } catch (error) {
        if (created) {
          if (file.exists) file.delete()
          if (media.exists) media.delete()
        }
        throw error
      }
    },
    list() {
      const files = directory('files')
      const types = directory('types')
      if (!files.exists || !types.exists) return []
      const saved: SavedReport[] = []
      for (const entry of files.list()) {
        if (!(entry instanceof File)) continue
        if (!isSafeReportName(entry.name)) continue
        const media = new File(types, entry.name)
        if (!media.exists) continue
        saved.push({ name: entry.name, mediaType: media.textSync(), size: entry.size })
      }
      saved.sort((left, right) => left.name.localeCompare(right.name))
      return saved
    },
    get(name): OpticalFile | undefined {
      if (!isSafeReportName(name)) return undefined
      const file = reportFile(name)
      const media = typeFile(name)
      if (!file.exists || !media.exists) return undefined
      return { name, mediaType: media.textSync(), payload: Uint8Array.from(file.bytesSync()) }
    },
    remove(name) {
      if (!isSafeReportName(name)) return
      const file = reportFile(name)
      const media = typeFile(name)
      if (file.exists) file.delete()
      if (media.exists) media.delete()
    },
    uri(name) {
      if (!isSafeReportName(name)) return undefined
      const file = reportFile(name)
      if (!file.exists) return undefined
      return file.uri
    },
  }
}
