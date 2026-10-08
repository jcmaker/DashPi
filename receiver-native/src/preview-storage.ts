import { Directory, File, Paths } from 'expo-file-system'
import type { PreviewModel } from './preview-model'

export type WrittenPreview = {
  htmlUri: string | null
  readAccessUri: string | null
  videoUris: string[]
}

function previewDirectory(): Directory {
  const root = new Directory(Paths.cache, 'dashpi-preview')
  if (root.exists) root.delete()
  root.create({ intermediates: true })
  return root
}

function writeBytes(directory: Directory, name: string, content: string | Uint8Array): string {
  const file = new File(directory, name)
  file.create()
  file.write(content)
  return file.uri
}

export function writePreview(model: PreviewModel, payload: Uint8Array): WrittenPreview {
  if (model.kind === 'message' || model.kind === 'native-report') {
    return { htmlUri: null, readAccessUri: null, videoUris: [] }
  }
  const root = previewDirectory()
  if (model.kind === 'video') {
    return {
      htmlUri: null,
      readAccessUri: root.uri,
      videoUris: [writeBytes(root, model.filename, payload)],
    }
  }
  return {
    htmlUri: writeBytes(root, 'preview.html', model.html),
    readAccessUri: root.uri,
    videoUris: model.videos.map((video) => writeBytes(root, video.filename, video.bytes)),
  }
}
