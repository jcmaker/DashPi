import { requireNativeModule } from 'expo'

type DashpiShareNative = {
  shareAsync(uri: string, mimeType: string, dialogTitle: string): Promise<void>
}

const DashpiShare = requireNativeModule<DashpiShareNative>('DashpiShare')

export function presentShareSheet(uri: string, mimeType: string): Promise<void> {
  return DashpiShare.shareAsync(uri, mimeType, '리포트 저장')
}
