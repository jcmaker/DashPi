import { messageForFrameError } from '../../web/src/optical/frame-error.ts'

export type ScanPhase = 'scanning' | 'receiving' | 'verifying' | 'verified'

export type FrameMark = {
  sessionId: number
  sequence: number
}

/** Pi and the sender advance the on-screen QR on this cadence. */
export const SENDER_FRAME_INTERVAL_MS = 250

/**
 * A gap this long means frames stopped. It is many sender intervals, so a
 * missed symbol or a brief blur does not abort a transfer that is still moving.
 */
export const FRAME_STALL_MS = SENDER_FRAME_INTERVAL_MS * 32

export const STALL_MESSAGE = '새 QR 프레임이 오지 않습니다. 새로 받으세요.'

export { messageForFrameError }

export function screenShouldStayAwake(phase: ScanPhase): boolean {
  return phase === 'scanning' || phase === 'receiving' || phase === 'verifying'
}

/** In-progress collection can be discarded. Verified results keep their own control. */
export function offerDiscard(phase: ScanPhase, error?: string): boolean {
  if (phase === 'verified') return false
  return phase === 'receiving' || phase === 'verifying' || Boolean(error)
}

/** A repeated read of the same QR is not evidence that the sender is still advancing. */
export function isFreshFrame(previous: FrameMark | null, next: FrameMark): boolean {
  if (previous == null) return true
  return previous.sessionId !== next.sessionId || previous.sequence !== next.sequence
}

export function stallMessage(
  phase: ScanPhase,
  lastFreshAt: number | null,
  now: number,
): string | undefined {
  if (phase !== 'receiving' || lastFreshAt == null) return undefined
  if (now - lastFreshAt < FRAME_STALL_MS) return undefined
  return STALL_MESSAGE
}
