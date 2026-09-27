export function androidApkPath(base?: string): string {
  const root = base ? base : '/DashPi/receiver/'
  const prefix = root.endsWith('/') ? root : `${root}/`
  return `${prefix}DashPi.apk`
}
