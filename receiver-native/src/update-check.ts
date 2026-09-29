// Pages publishes this manifest together with the signed APK.
const APK_BASE_URL = 'https://jcmaker.github.io/DashPi/receiver'
export const VERSION_URL = `${APK_BASE_URL}/version.json`

export type Update = { version: string; url: string }

export const UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000

export type UpdateCooldown = { shownAt: number; due: boolean }

// The interval starts only after the update dialog is shown. A failure or a
// check that finds nothing leaves shownAt alone, so the next foreground can retry.
export function updateCooldown(
  shownAt: number,
  now: number,
  dialogShown: boolean,
  intervalMs = UPDATE_CHECK_INTERVAL_MS,
): UpdateCooldown {
  const nextShownAt = dialogShown ? now : shownAt
  return { shownAt: nextShownAt, due: now - nextShownAt >= intervalMs }
}

type Version = [number, number, number]

export function parseVersion(text: string): Version | null {
  const match = /^(?:app-v)?(\d+)\.(\d+)\.(\d+)$/.exec(text.trim())
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null
}

export function isNewer(candidate: string, current: string): boolean {
  const next = parseVersion(candidate)
  const now = parseVersion(current)
  if (!next || !now) return false
  for (let index = 0; index < 3; index += 1) {
    if (next[index] !== now[index]) return next[index] > now[index]
  }
  return false
}

// Never throws: offline, rate limits, or odd replies simply mean "no update to offer".
export async function checkForUpdate(
  current: string | null,
  fetcher: (url: string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Update | null> {
  if (!current || !parseVersion(current)) return null
  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), 8000)
  try {
    const response = await fetcher(VERSION_URL, { signal: timeout.signal })
    if (!response.ok) return null
    const manifest = await response.json()
    const version = manifest?.version
    return typeof version === 'string' && isNewer(version, current)
      ? { version, url: `${APK_BASE_URL}/DashPi.apk?v=${version}` }
      : null
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}
