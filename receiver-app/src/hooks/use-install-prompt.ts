import { useCallback, useEffect, useRef, useState } from 'react'

type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }

const INSTALLED_DISPLAY_MODES = ['standalone', 'window-controls-overlay']

export function isInstalledDisplay(matches: (query: string) => boolean, iosStandalone: boolean): boolean {
  if (matches('(display-mode: browser)')) return false
  return iosStandalone || INSTALLED_DISPLAY_MODES.some((mode) => matches(`(display-mode: ${mode})`))
}

function readInstalled(): boolean {
  return isInstalledDisplay(
    (query) => window.matchMedia(query).matches,
    (navigator as Navigator & { standalone?: boolean }).standalone === true,
  )
}

export function useInstallPrompt() {
  const [installed, setInstalled] = useState(readInstalled)
  const [accepted, setAccepted] = useState(false)
  const [promptEvent, setPromptEvent] = useState<InstallPromptEvent | undefined>(undefined)
  const waiting = useRef(false)
  const isIos =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

  useEffect(() => {
    const queries = ['browser', ...INSTALLED_DISPLAY_MODES].map((mode) => window.matchMedia(`(display-mode: ${mode})`))
    const refresh = () => setInstalled(readInstalled())
    for (const query of queries) query.addEventListener('change', refresh)

    const onPrompt = (event: Event) => {
      event.preventDefault()
      setPromptEvent(event as InstallPromptEvent)
    }
    const onInstalled = () => {
      setAccepted(true)
      setPromptEvent(undefined)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      for (const query of queries) query.removeEventListener('change', refresh)
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const install = useCallback(async () => {
    if (!promptEvent) {
      waiting.current = true
      return
    }
    waiting.current = false
    await promptEvent.prompt()
    const choice = await promptEvent.userChoice
    setPromptEvent(undefined)
    if (choice.outcome === 'accepted') setAccepted(true)
  }, [promptEvent])

  useEffect(() => {
    if (promptEvent && waiting.current) void install()
  }, [install, promptEvent])

  return { installed, accepted, canPrompt: promptEvent !== undefined, isIos, install }
}
