import { requireNativeModule } from 'expo'

type DashpiShareNative = {
  shareAsync(uri: string, mimeType: string, dialogTitle: string): Promise<void>
  openInChromeAsync(url: string): Promise<boolean>
  getSystemInsetsAsync(): Promise<{ top: number; bottom: number; left: number; right: number }>
}

const DashpiShare = requireNativeModule<DashpiShareNative>('DashpiShare')

export function presentShareSheet(uri: string, mimeType: string): Promise<void> {
  return DashpiShare.shareAsync(uri, mimeType, '리포트 저장')
}

/** Android only. Resolves false when Chrome is not installed. */
export function openInChrome(url: string): Promise<boolean> {
  return DashpiShare.openInChromeAsync(url)
}

/** Android system bars and display cutouts, in density-independent units. */
export function getSystemInsets(): Promise<{ top: number; bottom: number; left: number; right: number }> {
  return DashpiShare.getSystemInsetsAsync()
}
