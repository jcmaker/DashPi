const CONSTRAINTS: MediaStreamConstraints = { video: { facingMode: { ideal: 'environment' } }, audio: false }

export function isCameraPermissionError(error: unknown): boolean {
  return (
    error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')
  )
}

export function requestCamera(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia(CONSTRAINTS)
}
