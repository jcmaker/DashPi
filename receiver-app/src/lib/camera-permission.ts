// video: true is the request both browsers will turn into a permission prompt.
// A rear-camera constraint here can fail before that prompt appears.
export const cameraConstraints: MediaStreamConstraints = { audio: false, video: true }

export function isCameraPermissionError(error: unknown): boolean {
  return (
    error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')
  )
}

export async function requestCamera(): Promise<MediaStream> {
  const devices = navigator.mediaDevices
  if (!devices?.getUserMedia) throw new DOMException('camera unavailable', 'NotSupportedError')
  const stream = await devices.getUserMedia(cameraConstraints)
  const [track] = stream.getVideoTracks()
  if (track) await track.applyConstraints({ facingMode: 'environment' }).catch(() => undefined)
  return stream
}
