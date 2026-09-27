export type CameraGate = 'checking' | 'request' | 'settings' | 'scan'

export function cameraGate(
  permission: { granted: boolean; canAskAgain: boolean } | null,
): CameraGate {
  if (!permission) return 'checking'
  if (permission.granted) return 'scan'
  return permission.canAskAgain ? 'request' : 'settings'
}
