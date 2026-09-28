export type ShareableReport = {
  name: string
  mediaType: string
  payload: Uint8Array
}

export type CacheFile = {
  readonly exists: boolean
  readonly uri: string
  delete(): void
  create(): void
  write(content: Uint8Array): void
}

export type ShareDialogOptions = {
  mimeType: string
  dialogTitle: string
  UTI: string
}

export type ShareAttemptDeps = {
  open(name: string): CacheFile
  shareAsync(uri: string, options: ShareDialogOptions): Promise<void>
}

export type ShareOutcome =
  | { status: 'shared' }
  | { status: 'busy' }
  | { status: 'failed'; reason: string }

function dialogOptions(mediaType: string): ShareDialogOptions {
  return {
    mimeType: mediaType,
    dialogTitle: '리포트 저장',
    UTI: mediaType === 'text/html' ? 'public.html' : 'public.data',
  }
}

function failureReason(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return '리포트를 공유하지 못했습니다.'
}

export function applyShareOutcome<T extends { error?: string }>(screen: T, outcome: ShareOutcome): T {
  if (outcome.status === 'failed') return { ...screen, error: outcome.reason }
  if (outcome.status === 'shared') return { ...screen, error: undefined }
  return screen
}

export function createShareAttempt(deps: ShareAttemptDeps) {
  let inProgress = false
  return async function attemptShare(file: ShareableReport): Promise<ShareOutcome> {
    if (inProgress) return { status: 'busy' }
    inProgress = true
    try {
      const stored = deps.open(file.name)
      if (stored.exists) stored.delete()
      stored.create()
      stored.write(file.payload)
      await deps.shareAsync(stored.uri, dialogOptions(file.mediaType))
      return { status: 'shared' }
    } catch (error) {
      return { status: 'failed', reason: failureReason(error) }
    } finally {
      inProgress = false
    }
  }
}
