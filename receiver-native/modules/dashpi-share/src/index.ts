import { requireNativeModule } from 'expo'

type DashpiShareNative = {
  shareAsync(uri: string, mimeType: string, dialogTitle: string): Promise<void>
  openInChromeAsync(url: string): Promise<boolean>
}

const DashpiShare = requireNativeModule<DashpiShareNative>('DashpiShare')

export function presentShareSheet(uri: string, mimeType: string): Promise<void> {
  return DashpiShare.shareAsync(uri, mimeType, '리포트 저장')
}

/** Android only. Resolves false when Chrome is not installed. */
export function openInChrome(url: string): Promise<boolean> {
  return DashpiShare.openInChromeAsync(url)
}
