const CONSTRAINTS: MediaStreamConstraints = { video: { facingMode: { ideal: 'environment' } }, audio: false }

export function isCameraPermissionError(error: unknown): boolean {
  return (
    error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')
  )
}

export function cameraSettingsUrl(userAgent: string, origin: string): string {
  if (/iPhone|iPad|iPod/i.test(userAgent)) return 'app-settings:'
  if (/Android/i.test(userAgent)) {
    const packageName = /SamsungBrowser/i.test(userAgent)
      ? 'com.sec.android.app.sbrowser'
      : /EdgA\//i.test(userAgent)
        ? 'com.microsoft.emmx'
        : /Firefox/i.test(userAgent)
          ? 'org.mozilla.firefox'
          : 'com.android.chrome'
    return `intent:#Intent;action=android.settings.APPLICATION_DETAILS_SETTINGS;category=android.intent.category.DEFAULT;data=package:${packageName};end`
  }
  const scheme = /Edg\//i.test(userAgent) ? 'edge' : 'chrome'
  return `${scheme}://settings/content/siteDetails?site=${encodeURIComponent(origin)}`
}

export function requestCamera(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia(CONSTRAINTS)
}
