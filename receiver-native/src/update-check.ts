// Finds a newer DashPi APK among this repo's GitHub releases (tags `app-vX.Y.Z`).
export const RELEASES_URL = 'https://api.github.com/repos/jcmaker/DashPi/releases?per_page=30'
const TAG_PREFIX = 'app-v'
const APK_NAME = 'DashPi.apk'

export type Release = {
  tag_name: string
  draft: boolean
  prerelease: boolean
  assets: { name: string; browser_download_url: string }[]
}

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

export function pickUpdate(releases: Release[], current: string): Update | null {
  let best: Update | null = null
  for (const release of releases) {
    if (release.draft || release.prerelease || !release.tag_name.startsWith(TAG_PREFIX)) continue
    const version = release.tag_name.slice(TAG_PREFIX.length)
    const apk = release.assets.find((asset) => asset.name === APK_NAME)
    if (!apk || !parseVersion(version) || !isNewer(version, best?.version ?? current)) continue
    best = { version, url: apk.browser_download_url }
  }
  return best
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
    const response = await fetcher(RELEASES_URL, {
      headers: { Accept: 'application/vnd.github+json' },
      signal: timeout.signal,
    })
    if (!response.ok) return null
    const releases = await response.json()
    return Array.isArray(releases) ? pickUpdate(releases, current) : null
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}
