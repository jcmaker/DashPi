import { useCallback, useEffect, useRef, useState } from 'react'
import { CameraView, useCameraPermissions } from 'expo-camera'
import { StatusBar } from 'expo-status-bar'
import * as Application from 'expo-application'
import { Alert, AppState, Linking, Pressable, StyleSheet, Text, View } from 'react-native'
import { WebView } from 'react-native-webview'
import { bytesFromBarcode } from './src/barcode'
import { cameraGate } from './src/camera-gate'
import { unpackNativeContainer } from './src/native-container'
import type { OpticalFile } from './src/unpack'
import { shareReceivedReport } from './src/share-sheet'
import { checkForUpdate } from './src/update-check'
import { FrameCollector, messageForFrameError } from '../web/src/optical/collector.ts'
import { parseFrame } from '../web/src/optical/protocol.ts'

type Phase = 'scanning' | 'receiving' | 'verifying' | 'verified'

type Screen = {
  phase: Phase
  recovered: number
  total: number
  error?: string
  file?: OpticalFile
  html?: string
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
      <Text style={styles.kicker}>DashPi</Text>
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

function Receiver() {
  const collector = useRef(new FrameCollector())
  const busy = useRef(false)
  const generation = useRef(0)
  const [screen, setScreen] = useState<Screen>(initialScreen)

  const reset = useCallback(() => {
    generation.current += 1
    busy.current = false
    collector.current = new FrameCollector()
    setScreen(initialScreen)
  }, [])

  const onBarcodeScanned = useCallback(({ data }: { data: string }) => {
    if (busy.current) return
    let bytes: Uint8Array
    try {
      bytes = bytesFromBarcode(data)
    } catch {
      return
    }

    const frames = collector.current
    let packed: Uint8Array | undefined
    try {
      packed = frames.add(parseFrame(bytes))
    } catch (problem) {
      const message = messageForFrameError(problem)
      if (message) setScreen((current) => ({ ...current, error: message }))
      return
    }

    const { recovered, total } = frames.progress
    if (!packed) {
      setScreen({ phase: 'receiving', recovered, total })
      return
    }

    busy.current = true
    const ticket = generation.current
    const identity = frames.identity
    setScreen({ phase: 'verifying', recovered, total })
    void unpackNativeContainer(packed)
      .then((file) => {
        if (ticket !== generation.current || frames.identity !== identity) return
        const html = file.mediaType === 'text/html' ? new TextDecoder().decode(file.payload) : undefined
        setScreen({ phase: 'verified', recovered, total, file, html })
      })
      .catch(() => {
        if (ticket !== generation.current) return
        busy.current = false
        collector.current = new FrameCollector()
        setScreen({
          phase: 'scanning',
          recovered: 0,
          total: 0,
          error: '받은 데이터를 열 수 없습니다. 화면을 다시 비추세요.',
        })
      })
  }, [])

  const share = useCallback(() => {
    const file = screen.file
    if (!file) return
    void shareReceivedReport(file).catch(() => undefined)
  }, [screen.file])

  const percent = screen.total > 0 ? Math.round((screen.recovered / screen.total) * 100) : 0
  const scanning = screen.phase !== 'verified'

  return (
    <View style={styles.screen}>
      <Text style={styles.kickerLight}>DashPi</Text>
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
        <View style={styles.preview}>
          {screen.html ? (
            <WebView originWhitelist={['*']} source={{ html: screen.html }} style={styles.web} />
          ) : (
            <Text style={styles.bodyDark}>
              {screen.file?.name} 검증이 끝났습니다. 공유해서 여세요.
            </Text>
          )}
        </View>
      )}
      <Text style={styles.status}>
        {screen.phase === 'scanning' && 'DashPi QR 화면을 카메라 안에 맞추세요.'}
        {screen.phase === 'receiving' && `수신 중 ${screen.recovered}/${screen.total} · ${percent}%`}
        {screen.phase === 'verifying' && 'SHA-256 무결성을 검증하고 있습니다.'}
        {screen.phase === 'verified' &&
          `${screen.file?.name ?? '리포트'} · ${formatBytes(screen.file?.payload.length ?? 0)} 검증 완료`}
      </Text>
      {screen.phase === 'receiving' && (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${percent}%` }]} />
        </View>
      )}
      {screen.error && <Text style={styles.error}>{screen.error}</Text>}
      {screen.phase === 'verified' && (
        <View style={styles.actions}>
          <Pressable style={styles.primary} onPress={share}>
            <Text style={styles.primaryLabel}>공유 또는 파일에 저장</Text>
          </Pressable>
          <Pressable style={styles.secondary} onPress={reset}>
            <Text style={styles.secondaryLabel}>새로 받기</Text>
          </Pressable>
        </View>
      )}
    </View>
  )
}

const UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000

function useUpdatePrompt() {
  const lastCheck = useRef(0)
  const check = useCallback(async () => {
    if (Date.now() - lastCheck.current < UPDATE_CHECK_INTERVAL_MS) return
    lastCheck.current = Date.now()
    const update = await checkForUpdate(Application.nativeApplicationVersion)
    if (!update) return
    Alert.alert(
      '새 버전이 있어요',
      `DashPi ${update.version}이 나왔어요. 지금 받아서 설치할까요?`,
      [
        { text: '나중에', style: 'cancel' },
        { text: '업데이트', onPress: () => void Linking.openURL(update.url) },
      ],
    )
  }, [])
  return check
}

export default function App() {
  const [permission, requestPermission, getPermission] = useCameraPermissions()
  const checkUpdate = useUpdatePrompt()

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
      {gate === 'scan' && <Receiver />}
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
  bodyDark: { color: '#e2e8f0', fontSize: 16, lineHeight: 24 },
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
  web: { flex: 1, backgroundColor: '#ffffff' },
  status: { color: '#e2e8f0', fontSize: 15, marginTop: 16 },
  track: { height: 8, borderRadius: 4, backgroundColor: '#1e293b', marginTop: 12, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: '#38bdf8' },
  error: { color: '#fecaca', fontSize: 14, marginTop: 12 },
  actions: { gap: 10, marginTop: 16 },
})
