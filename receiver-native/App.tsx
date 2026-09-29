import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useEvent } from 'expo'
import { CameraView, useCameraPermissions } from 'expo-camera'
import { useKeepAwake } from 'expo-keep-awake'
import { StatusBar } from 'expo-status-bar'
import * as Application from 'expo-application'
import { useVideoPlayer, VideoView } from 'expo-video'
import { Alert, AppState, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { WebView } from 'react-native-webview'
import { verifiedHtmlWebViewProps } from './src/webview-policy'
import { handleBarcodeScan, type BarcodeScan } from './src/barcode'
import { cameraGate } from './src/camera-gate'
import { documentReportStore } from './src/document-reports'
import {
  ReportSaveError,
  saveVerifiedReport,
  type ReportStore,
  type SavedReport,
} from './src/saved-reports'
import { unpackNativeContainer } from './src/native-container'
import type { OpticalFile } from './src/unpack'
import { checkForUpdate, updateCooldown } from './src/update-check'
import {
  PLAYBACK_UNAVAILABLE,
  PREVIEW_OPEN_FAILED,
  PREVIEW_PREPARING,
  previewForFile,
} from './src/preview-model'
import { writePreview, type WrittenPreview } from './src/preview-storage'
import { FrameCollector } from '../web/src/optical/collector.ts'
import {
  FRAME_STALL_MS,
  type FrameMark,
  isFreshFrame,
  offerDiscard,
  screenShouldStayAwake,
  stallMessage,
} from './src/scan-session'
import { applyShareOutcome, shareReport } from './src/share-sheet'

type Phase = 'scanning' | 'receiving' | 'verifying' | 'verified'

type Screen = {
  phase: Phase
  recovered: number
  total: number
  error?: string
  file?: OpticalFile
}

const initialScreen: Screen = { phase: 'scanning', recovered: 0, total: 0 }

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function PermissionScreen({
  canAskAgain,
  onAllow,
  onSettings,
}: {
  canAskAgain: boolean
  onAllow: () => void
  onSettings: () => void
}) {
  return (
    <View style={styles.gate}>
      <Text style={styles.kicker}>DashPi · v{Application.nativeApplicationVersion ?? '개발'}</Text>
      <Text style={styles.title}>사고 리포트 받기</Text>
      <Text style={styles.body}>
        {canAskAgain
          ? '카메라 시작을 누르면 허용 창이 뜹니다. 허용하면 DashPi 화면의 QR을 읽어 리포트를 받습니다.'
          : '이 기기는 허용 창을 다시 띄우지 않습니다. 설정에서 카메라를 허용한 뒤 돌아오면 바로 받을 수 있습니다.'}
      </Text>
      <Pressable style={styles.primary} onPress={canAskAgain ? onAllow : onSettings}>
        <Text style={styles.primaryLabel}>{canAskAgain ? '카메라 시작' : '설정 열기'}</Text>
      </Pressable>
    </View>
  )
}

const KEEP_AWAKE_TAG = 'dashpi-optical-receive'

function ScanKeepAwake() {
  useKeepAwake(KEEP_AWAKE_TAG, { suppressDeactivateWarnings: true })
  return null
}

function ClipPlayer({ uri, fill }: { uri: string; fill: boolean }) {
  const player = useVideoPlayer(uri, (instance) => {
    instance.loop = false
  })
  const { status } = useEvent(player, 'statusChange', { status: player.status })
  if (status === 'error') return <Text style={styles.previewMessage}>{PLAYBACK_UNAVAILABLE}</Text>
  return (
    <View style={fill ? styles.clipFill : styles.clip}>
      <VideoView style={styles.clipVideo} player={player} nativeControls contentFit="contain" />
      <View style={styles.transport}>
        <Pressable style={styles.transportButton} onPress={() => player.play()}>
          <Text style={styles.transportLabel}>재생</Text>
        </Pressable>
        <Pressable style={styles.transportButton} onPress={() => player.pause()}>
          <Text style={styles.transportLabel}>일시정지</Text>
        </Pressable>
      </View>
    </View>
  )
}

function VerifiedPreview({ file }: { file: OpticalFile }) {
  const model = useMemo(() => previewForFile(file), [file])
  const [stored, setStored] = useState<WrittenPreview | null>(null)
  const [prepareError, setPrepareError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setStored(null)
    setPrepareError(false)
    try {
      const written = writePreview(model, file.payload)
      if (!cancelled) setStored(written)
    } catch {
      if (!cancelled) setPrepareError(true)
    }
    return () => {
      cancelled = true
    }
  }, [file, model])

  if (model.kind === 'message') {
    return (
      <View style={styles.preview}>
        <Text style={styles.previewMessage}>{model.message}</Text>
      </View>
    )
  }

  return (
    <View style={styles.preview}>
      {model.kind === 'html' && model.playbackNotice ? (
        <Text style={styles.previewMessage}>{model.playbackNotice}</Text>
      ) : null}
      {prepareError ? <Text style={styles.previewMessage}>{PREVIEW_OPEN_FAILED}</Text> : null}
      {!stored && !prepareError ? <Text style={styles.previewMessage}>{PREVIEW_PREPARING}</Text> : null}
      {stored?.videoUris.map((uri) => (
        <ClipPlayer key={uri} uri={uri} fill={model.kind === 'video'} />
      ))}
      {model.kind === 'html' ? (
        <View style={styles.webSlot}>
          <WebView {...verifiedHtmlWebViewProps(model.html)} style={styles.web} />
        </View>
      ) : null}
    </View>
  )
}

function Receiver({
  store,
  saved,
  reloadSaved,
}: {
  store: ReportStore
  saved: SavedReport[]
  reloadSaved: () => void
}) {
  const collector = useRef(new FrameCollector())
  const busy = useRef(false)
  const generation = useRef(0)
  const lastMark = useRef<FrameMark | null>(null)
  const lastFreshAt = useRef<number | null>(null)
  const stallTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const halted = useRef(false)
  const [screen, setScreen] = useState<Screen>(initialScreen)
  const [scanNotice, setScanNotice] = useState<string | null>(null)

  const clearStall = useCallback(() => {
    if (stallTimer.current != null) {
      clearTimeout(stallTimer.current)
      stallTimer.current = null
    }
  }, [])

  const armStall = useCallback(
    (at: number) => {
      clearStall()
      lastFreshAt.current = at
      stallTimer.current = setTimeout(() => {
        setScreen((current) => {
          const message = stallMessage(current.phase, lastFreshAt.current, Date.now())
          if (!message || current.error) return current
          return { ...current, error: message }
        })
      }, FRAME_STALL_MS)
    },
    [clearStall],
  )

  const forgetCollection = useCallback(() => {
    collector.current = new FrameCollector()
    lastMark.current = null
    lastFreshAt.current = null
    halted.current = false
    clearStall()
  }, [clearStall])

  const reset = useCallback(() => {
    generation.current += 1
    busy.current = false
    forgetCollection()
    setScreen(initialScreen)
    setScanNotice(null)
  }, [forgetCollection])

  useEffect(() => () => clearStall(), [clearStall])

  const onBarcodeScanned = useCallback((scan: BarcodeScan) => {
    if (busy.current || halted.current) return
    const frames = collector.current
    const outcome = handleBarcodeScan(frames, scan)
    if (outcome.status === 'ignore' || outcome.status === 'drop') {
      setScanNotice(
        Platform.OS === 'android' && !scan.rawBytesBase64
          ? 'QR은 감지됐지만 원본 데이터를 받지 못했습니다.'
          : 'QR은 감지됐지만 유효한 DashPi 프레임을 기다리고 있습니다.',
      )
      return
    }
    setScanNotice(null)
    if (outcome.status === 'error') {
      clearStall()
      halted.current = true
      setScreen((current) => ({ ...current, error: outcome.message }))
      return
    }

    const fresh = isFreshFrame(lastMark.current, outcome)
    if (fresh) lastMark.current = { sessionId: outcome.sessionId, sequence: outcome.sequence }
    const { recovered, total } = outcome
    if (outcome.status === 'progress') {
      if (fresh) armStall(Date.now())
      setScreen((current) => {
        if (!fresh && current.error) return current
        return { phase: 'receiving', recovered, total }
      })
      return
    }

    clearStall()
    busy.current = true
    const ticket = generation.current
    const identity = frames.identity
    setScreen({ phase: 'verifying', recovered, total })
    void saveVerifiedReport(outcome.packed, unpackNativeContainer, store)
      .then((file) => {
        if (ticket !== generation.current || frames.identity !== identity) return
        reloadSaved()
        setScreen({ phase: 'verified', recovered, total, file })
      })
      .catch((problem: unknown) => {
        if (ticket !== generation.current) return
        busy.current = false
        forgetCollection()
        setScreen({
          phase: 'scanning',
          recovered: 0,
          total: 0,
          error:
            problem instanceof ReportSaveError
              ? '리포트를 앱에 저장하지 못했습니다. 화면을 다시 비추세요.'
              : '받은 데이터를 열 수 없습니다. 화면을 다시 비추세요.',
        })
      })
  }, [armStall, clearStall, forgetCollection, reloadSaved, store])

  const openSaved = useCallback(
    (name: string) => {
      const stored = store.get(name)
      if (!stored) {
        reloadSaved()
        return
      }
      generation.current += 1
      busy.current = false
      forgetCollection()
      setScreen({ phase: 'verified', recovered: 0, total: 0, file: stored })
    },
    [forgetCollection, reloadSaved, store],
  )

  const deleteSaved = useCallback(
    (name: string) => {
      store.remove(name)
      reloadSaved()
      setScreen((current) => {
        if (current.file?.name !== name) return current
        generation.current += 1
        busy.current = false
        forgetCollection()
        return initialScreen
      })
    },
    [forgetCollection, reloadSaved, store],
  )

  const share = useCallback(() => {
    const file = screen.file
    if (!file) return
    void shareReport(file).then((outcome) => {
      setScreen((current) => {
        if (current.phase !== 'verified' || current.file !== file) return current
        return applyShareOutcome(current, outcome)
      })
    })
  }, [screen.file])

  const percent = screen.total > 0 ? Math.round((screen.recovered / screen.total) * 100) : 0
  const scanning = screen.phase !== 'verified'
  const discard = offerDiscard(screen.phase, screen.error)

  return (
    <View style={styles.screen}>
      {screenShouldStayAwake(screen.phase) ? <ScanKeepAwake /> : null}
      <Text style={styles.kickerLight}>DashPi · v{Application.nativeApplicationVersion ?? '개발'}</Text>
      <Text style={styles.titleLight}>사고 리포트 받기</Text>
      {scanning ? (
        <View style={styles.cameraFrame}>
          <CameraView
            style={styles.camera}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onBarcodeScanned={onBarcodeScanned}
          />
        </View>
      ) : (
        screen.file ? <VerifiedPreview file={screen.file} /> : null
      )}
      <Text style={styles.status}>
        {screen.phase === 'scanning' && 'DashPi QR 화면을 카메라 안에 맞추세요.'}
        {screen.phase === 'receiving' && `수신 중 ${screen.recovered}/${screen.total} · ${percent}%`}
        {screen.phase === 'verifying' && 'SHA-256 무결성을 검증하고 있습니다.'}
        {screen.phase === 'verified' &&
          `${screen.file?.name ?? '리포트'} · ${formatBytes(screen.file?.payload.length ?? 0)} 검증 완료 · 앱에 저장됨`}
      </Text>
      {screen.phase === 'scanning' && scanNotice && <Text style={styles.status}>{scanNotice}</Text>}
      {screen.phase === 'receiving' && (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${percent}%` }]} />
        </View>
      )}
      {screen.error && <Text style={styles.error}>{screen.error}</Text>}
      {discard && (
        <View style={styles.actions}>
          <Pressable style={styles.secondary} onPress={reset}>
            <Text style={styles.secondaryLabel}>새로 받기</Text>
          </Pressable>
        </View>
      )}
      {screen.phase === 'scanning' && saved.length > 0 && (
        <View style={styles.saved}>
          <Text style={styles.savedTitle}>저장된 리포트</Text>
          <ScrollView style={styles.savedList} nestedScrollEnabled>
            {saved.map((item) => (
              <View key={item.name} style={styles.savedRow}>
                <Text style={styles.savedName} numberOfLines={1}>
                  {item.name}
                </Text>
                <Pressable style={styles.savedOpen} onPress={() => openSaved(item.name)}>
                  <Text style={styles.savedOpenLabel}>열기</Text>
                </Pressable>
                <Pressable style={styles.savedDelete} onPress={() => deleteSaved(item.name)}>
                  <Text style={styles.savedDeleteLabel}>삭제</Text>
                </Pressable>
              </View>
            ))}
          </ScrollView>
        </View>
      )}
      {screen.phase === 'verified' && (
        <View style={styles.actions}>
          <Pressable style={styles.primary} onPress={share}>
            <Text style={styles.primaryLabel}>공유 또는 파일에 저장</Text>
          </Pressable>
          <Pressable style={styles.secondary} onPress={() => screen.file && deleteSaved(screen.file.name)}>
            <Text style={styles.secondaryLabel}>저장본 삭제</Text>
          </Pressable>
          <Pressable style={styles.secondary} onPress={reset}>
            <Text style={styles.secondaryLabel}>새로 받기</Text>
          </Pressable>
        </View>
      )}
    </View>
  )
}

function useUpdatePrompt() {
  const shownAt = useRef(0)
  const checking = useRef(false)
  const check = useCallback(async () => {
    const now = Date.now()
    if (checking.current || !updateCooldown(shownAt.current, now, false).due) return
    checking.current = true
    try {
      const update = await checkForUpdate(Application.nativeApplicationVersion)
      if (!update) return
      shownAt.current = updateCooldown(shownAt.current, now, true).shownAt
      Alert.alert(
        '새 버전이 있어요',
        `DashPi ${update.version}이 나왔어요. 지금 받아서 설치할까요?`,
        [
          { text: '나중에', style: 'cancel' },
          { text: '업데이트', onPress: () => void Linking.openURL(update.url) },
        ],
      )
    } finally {
      checking.current = false
    }
  }, [])
  return check
}

export default function App() {
  const [permission, requestPermission, getPermission] = useCameraPermissions()
  const checkUpdate = useUpdatePrompt()
  const store = useRef(documentReportStore())
  const [saved, setSaved] = useState<SavedReport[]>([])
  const reloadSaved = useCallback(() => {
    try {
      setSaved(store.current.list())
    } catch {
      setSaved([])
    }
  }, [])

  useEffect(() => {
    reloadSaved()
  }, [reloadSaved])

  useEffect(() => {
    void checkUpdate()
    const subscription = AppState.addEventListener('change', (state) => {
      if (state !== 'active') return
      void getPermission()
      void checkUpdate()
    })
    return () => subscription.remove()
  }, [getPermission, checkUpdate])

  const gate = cameraGate(permission)

  return (
    <View style={styles.root}>
      <StatusBar style={gate === 'scan' ? 'light' : 'dark'} />
      {gate === 'checking' && (
        <View style={styles.gate}>
          <Text style={styles.body}>카메라 권한을 확인하고 있습니다.</Text>
        </View>
      )}
      {gate === 'scan' && <Receiver store={store.current} saved={saved} reloadSaved={reloadSaved} />}
      {(gate === 'request' || gate === 'settings') && (
        <PermissionScreen
          canAskAgain={gate === 'request'}
          onAllow={() => void requestPermission()}
          onSettings={() => void Linking.openSettings()}
        />
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0f172a' },
  gate: {
    flex: 1,
    backgroundColor: '#f8fafc',
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingTop: 48,
  },
  screen: { flex: 1, paddingHorizontal: 20, paddingTop: 56, paddingBottom: 24 },
  kicker: { color: '#64748b', fontSize: 13, marginBottom: 8 },
  kickerLight: { color: '#94a3b8', fontSize: 13, marginBottom: 4 },
  title: { color: '#0f172a', fontSize: 28, fontWeight: '700', marginBottom: 12 },
  titleLight: { color: '#f8fafc', fontSize: 24, fontWeight: '700', marginBottom: 16 },
  body: { color: '#334155', fontSize: 16, lineHeight: 24, marginBottom: 24 },
  previewMessage: { color: '#0f172a', fontSize: 16, lineHeight: 24, padding: 16 },
  primary: {
    backgroundColor: '#2563eb',
    borderRadius: 12,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  primaryLabel: { color: '#ffffff', fontSize: 17, fontWeight: '600' },
  secondary: {
    borderColor: '#cbd5e1',
    borderRadius: 12,
    borderWidth: 1,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryLabel: { color: '#e2e8f0', fontSize: 17, fontWeight: '600' },
  cameraFrame: { flex: 1, borderRadius: 16, overflow: 'hidden', backgroundColor: '#020617' },
  camera: { flex: 1 },
  preview: { flex: 1, borderRadius: 16, overflow: 'hidden', backgroundColor: '#ffffff' },
  webSlot: { flex: 1 },
  web: { flex: 1, backgroundColor: '#ffffff' },
  clip: { height: 240, backgroundColor: '#020617' },
  clipFill: { flex: 1, backgroundColor: '#020617' },
  clipVideo: { flex: 1 },
  transport: { flexDirection: 'row', gap: 8, padding: 8 },
  transportButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    alignItems: 'center',
    justifyContent: 'center',
  },
  transportLabel: { color: '#f8fafc', fontSize: 16, fontWeight: '600' },
  status: { color: '#e2e8f0', fontSize: 15, marginTop: 16 },
  track: { height: 8, borderRadius: 4, backgroundColor: '#1e293b', marginTop: 12, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: '#38bdf8' },
  error: { color: '#fecaca', fontSize: 14, marginTop: 12 },
  actions: { gap: 10, marginTop: 16 },
  saved: { marginTop: 12 },
  savedTitle: { color: '#94a3b8', fontSize: 13, marginBottom: 8 },
  savedList: { maxHeight: 160 },
  savedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  savedName: { color: '#f8fafc', flex: 1, fontSize: 15 },
  savedOpen: {
    borderColor: '#38bdf8',
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  savedOpenLabel: { color: '#e0f2fe', fontSize: 14, fontWeight: '600' },
  savedDelete: {
    borderColor: '#fecaca',
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  savedDeleteLabel: { color: '#fecaca', fontSize: 14, fontWeight: '600' },
})
