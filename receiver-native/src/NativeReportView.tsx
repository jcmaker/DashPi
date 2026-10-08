import { useEffect, useRef, useState } from 'react'
import { Image, Platform, Pressable, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View } from 'react-native'
import { getSystemInsets } from 'dashpi-share'
import { previewForFile } from './preview-model'
import { nearestKeyframe, relativeTimestamp, REVIEW_ITEMS, verifyReportImages, type KeyframeRole, type ValidatedNativeReport } from './native-report'
import { digestReportImage, shareReport } from './share-sheet'
import type { OpticalFile } from './unpack'

const ROLE_LABEL: Record<KeyframeRole, string> = { before: '사고 전', moment: '사고 순간', after: '사고 후' }
const STATUS_LABEL = { observed: '관찰됨', not_observed: '관찰되지 않음', not_determinable: '확인 불가' }

export function localReportTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' })
}

function Disclosure({ title, open, toggle }: { title: string; open: boolean; toggle: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={toggle} style={styles.disclosure}>
    <Text style={[styles.sectionTitle, styles.disclosureTitle]}>{title}</Text><Text style={styles.disclosureMark}>{open ? '접기 −' : '펼치기 +'}</Text>
  </Pressable>
}

export default function NativeReportView({ file, onNewReceive, onDelete }: {
  file: OpticalFile
  onNewReceive: () => void
  onDelete: () => void
}) {
  const [report, setReport] = useState<ValidatedNativeReport | null>(null)
  const [preparing, setPreparing] = useState(true)
  const [openError, setOpenError] = useState<string | null>(null)
  const [shareError, setShareError] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)
  const [decoded, setDecoded] = useState<KeyframeRole[]>([])
  const currentFile = useRef<OpticalFile | null>(file)
  const [selected, setSelected] = useState<KeyframeRole>('moment')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [insets, setInsets] = useState({ top: StatusBar.currentHeight ?? 0, bottom: 24, left: 0, right: 0 })

  useEffect(() => {
    if (Platform.OS !== 'android') return
    let cancelled = false
    void getSystemInsets().then((next) => { if (!cancelled) setInsets(next) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    currentFile.current = file
    void Promise.resolve().then(() => {
      if (cancelled) return null
      const model = previewForFile(file)
      if (model.kind !== 'native-report') throw new Error(model.kind === 'message' ? model.message : '리포트를 열 수 없습니다.')
      return verifyReportImages(model.report, digestReportImage)
    }).then((checked) => {
      if (cancelled || !checked) return
      setReport(checked)
      setPreparing(false)
    }).catch((error: unknown) => {
      if (cancelled) return
      setOpenError(error instanceof Error ? error.message : '리포트를 열 수 없습니다. 원본은 앱에 저장되어 공유할 수 있습니다.')
      setPreparing(false)
    })
    return () => { cancelled = true; currentFile.current = null }
  }, [file])

  const share = async () => {
    if (sharing || preparing || decoding) return
    setSharing(true)
    const result = await shareReport(file, report ?? undefined)
    if (currentFile.current !== file) return
    setSharing(false)
    if (result.status === 'failed') setShareError(result.reason)
    else if (result.status === 'shared') setShareError(null)
  }
  const imageFailed = (role: KeyframeRole) => {
    if (currentFile.current !== file) return
    setReport((current) => current ? { ...current, keyframes: current.keyframes.map((frame) => frame.role === role ? { ...frame, imageValid: false, imageError: '이미지 손상', dataUri: null } : frame) } : current)
  }
  const imageDecoded = (role: KeyframeRole) => {
    if (currentFile.current !== file) return
    setDecoded((current) => current.includes(role) ? current : [...current, role])
  }
  const decoding = report !== null && report.keyframes.some((frame) => frame.imageValid && !decoded.includes(frame.role))
  const image = report?.keyframes.find((frame) => frame.role === selected)
  const safeStyle = Platform.OS === 'android' ? { paddingTop: insets.top, paddingBottom: insets.bottom, paddingLeft: insets.left, paddingRight: insets.right } : undefined

  return <SafeAreaView style={[styles.safe, safeStyle]}>
    <StatusBar barStyle="dark-content" />
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <Text style={styles.kicker}>DashPi · 사고 리포트</Text>
      {preparing ? <Text accessibilityRole="text" accessibilityLiveRegion="polite" style={styles.body}>리포트와 이미지 무결성을 검증하고 있습니다.</Text> : null}
      {openError ? <Text accessibilityLiveRegion="polite" style={styles.body}>{openError}</Text> : null}
      {report ? <>
        {report.keyframes.filter((frame) => frame.imageValid && frame.dataUri).map((frame) => <Image key={`check-${frame.role}`} source={{ uri: frame.dataUri! }} style={styles.decodeCheck} accessible={false} onLoad={() => imageDecoded(frame.role)} onError={() => imageFailed(frame.role)} />)}
        <Text accessibilityRole="header" style={styles.title}>{localReportTime(report.triggered_at)}</Text>
        <Text style={styles.badge}>수신 파일 무결성 검증 완료 · 앱에 저장됨</Text>
        {report.keyframes.some((frame) => !frame.imageValid) ? <Text style={styles.warning}>일부 이미지가 손상되었습니다. 원본 수신 파일은 보관됩니다.</Text> : null}
        <View style={styles.imageBox}>
          {image?.imageValid && image.dataUri ? <Image key={image.role} source={{ uri: image.dataUri }} resizeMode="contain" style={styles.image} accessible accessibilityLabel={`${ROLE_LABEL[selected]} · ${relativeTimestamp(image.timestamp, report.incident_timestamp)}`} onLoad={() => imageDecoded(image.role)} onError={() => imageFailed(image.role)} /> : <Text style={styles.imageError}>이미지 손상 · {ROLE_LABEL[selected]}</Text>}
        </View>
        <View style={styles.tabs}>
          {(['before', 'moment', 'after'] as const).map((role) => {
            const frame = report.keyframes.find((entry) => entry.role === role)!
            return <Pressable key={role} accessibilityRole="button" accessibilityState={{ selected: selected === role }} accessibilityLabel={`${ROLE_LABEL[role]}, ${relativeTimestamp(frame.timestamp, report.incident_timestamp)}`} onPress={() => setSelected(role)} style={[styles.tab, selected === role && styles.tabSelected]}>
              <Text style={[styles.tabLabel, selected === role && styles.tabLabelSelected]}>{ROLE_LABEL[role]}</Text>
              <Text style={[styles.tabTime, selected === role && styles.tabLabelSelected]}>{relativeTimestamp(frame.timestamp, report.incident_timestamp)}</Text>
            </Pressable>
          })}
        </View>
        <Text accessibilityRole="header" style={styles.sectionTitle}>AI 요약</Text>
        <Text style={styles.body}>{report.summary}</Text>
        <Text accessibilityRole="header" style={styles.sectionTitle}>시간별 관찰</Text>
        {[...report.observations].sort((a, b) => a.timestamp - b.timestamp).map((observation, index) => {
          const role = nearestKeyframe(observation.timestamp, report.keyframes)
          const active = role === selected
          return <Pressable key={index} accessibilityRole="button" accessibilityLabel={`${relativeTimestamp(observation.timestamp, report.incident_timestamp)}, ${observation.description}, ${ROLE_LABEL[role]} 사진 보기`} accessibilityState={{ selected: active }} onPress={() => setSelected(role)} style={[styles.observation, active && styles.observationSelected]}>
            <Text style={styles.observationTime}>{relativeTimestamp(observation.timestamp, report.incident_timestamp)}</Text>
            <Text style={[styles.observationText, active && styles.observationTextSelected]}>{observation.description}</Text>
          </Pressable>
        })}
        <Text accessibilityRole="header" style={styles.sectionTitle}>영상으로 확인할 수 없는 내용</Text>
        {[...report.limitations, ...report.warnings].map((line, index) => <Text key={index} style={styles.body}>• {line}</Text>)}
        <Disclosure title="12대 중과실 관련 영상 확인" open={reviewOpen} toggle={() => setReviewOpen((value) => !value)} />
        <Text style={styles.note}>법적 판정이 아니라 관련 장면이 보였는지만 정리했습니다.</Text>
        {reviewOpen ? REVIEW_ITEMS.map(([key, label]) => {
          const entry = report.major_negligence_review[key]
          return <View key={key} style={styles.reviewItem}>
            <Text style={styles.reviewLabel}>{label}</Text>
            <Text style={[styles.chip, entry.status === 'observed' ? styles.observed : entry.status === 'not_observed' ? styles.notObserved : styles.notAssessable]}>{STATUS_LABEL[entry.status]}</Text>
            {entry.evidence ? <Text style={styles.body}>{entry.evidence}</Text> : null}
            {entry.timestamp !== null ? <Text style={styles.note}>{relativeTimestamp(entry.timestamp, report.incident_timestamp)}</Text> : null}
          </View>
        }) : null}
        <Text accessibilityRole="header" style={styles.sectionTitle}>긴급 번호</Text>
        <Text style={styles.body}>119 구급·소방 · 112 경찰</Text>
      </> : null}
      {!preparing ? <>
        <Disclosure title="증거 상세" open={detailsOpen} toggle={() => setDetailsOpen((value) => !value)} />
        {detailsOpen ? <View style={styles.details}>
          <Text selectable style={styles.body}>수신 파일: {file.name} · {file.payload.byteLength.toLocaleString()} B</Text>
          {report ? <>
            <Text selectable style={styles.body}>사고 ID: {report.incident_id}</Text>
            <Text style={styles.body}>생성 시각: {localReportTime(report.generated_at)}</Text>
            <Text style={styles.body}>모델: {report.model}</Text>
            {Object.entries(report.digests).map(([name, digest]) => <Text selectable key={name} style={styles.digest}>{name} SHA-256{ '\n' }{digest}</Text>)}
            {report.keyframes.map((frame) => <Text selectable key={frame.role} style={styles.digest}>{ROLE_LABEL[frame.role]} JPEG SHA-256{ '\n' }{frame.sha256}{!frame.imageValid ? '\n이미지 손상' : ''}</Text>)}
          </> : null}
          <Pressable accessibilityRole="button" onPress={onDelete} style={styles.deleteButton}><Text style={styles.deleteLabel}>저장본 삭제</Text></Pressable>
        </View> : null}
      </> : null}
    </ScrollView>
    <View style={styles.footer}>
      {shareError ? <Text accessibilityLiveRegion="polite" style={styles.shareError}>{shareError}</Text> : null}
      <View style={styles.footerButtons}>
        <Pressable accessibilityRole="button" accessibilityState={{ disabled: preparing || decoding || sharing }} disabled={preparing || decoding || sharing} onPress={() => void share()} style={[styles.shareButton, (preparing || decoding || sharing) && styles.disabled]}><Text style={styles.shareLabel}>{sharing ? '공유 준비 중…' : decoding ? '이미지 확인 중…' : '공유 또는 저장'}</Text></Pressable>
        <Pressable accessibilityRole="button" onPress={onNewReceive} style={styles.newButton}><Text style={styles.newLabel}>새로 받기</Text></Pressable>
      </View>
    </View>
  </SafeAreaView>
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f8fafc' },
  scroll: { flex: 1 }, content: { padding: 20, paddingBottom: 24 },
  kicker: { color: '#475569', fontSize: 14, marginBottom: 12 },
  title: { color: '#0f172a', fontSize: 25, fontWeight: '700', marginBottom: 10 },
  badge: { color: '#1e40af', backgroundColor: '#dbeafe', fontSize: 14, padding: 10, borderRadius: 8, marginBottom: 16 },
  body: { color: '#334155', fontSize: 17, lineHeight: 26, marginBottom: 12 },
  warning: { color: '#854d0e', backgroundColor: '#fef3c7', padding: 12, fontSize: 16, marginBottom: 12 },
  imageBox: { backgroundColor: '#0f172a', borderRadius: 12, overflow: 'hidden', aspectRatio: 16 / 9, justifyContent: 'center', alignItems: 'center' },
  image: { width: '100%', height: '100%' }, imageError: { color: '#f8fafc', fontSize: 18, padding: 16 },
  decodeCheck: { position: 'absolute', width: 1, height: 1, opacity: 0 },
  tabs: { flexDirection: 'row', gap: 8, marginTop: 10, marginBottom: 24 },
  tab: { flex: 1, minHeight: 64, paddingVertical: 12, paddingHorizontal: 4, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10 },
  tabSelected: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  tabLabel: { color: '#334155', fontSize: 16, fontWeight: '600', textAlign: 'center' },
  tabTime: { color: '#475569', fontSize: 14, marginTop: 4 }, tabLabelSelected: { color: '#ffffff' },
  sectionTitle: { color: '#0f172a', fontSize: 20, fontWeight: '700', marginTop: 12, marginBottom: 12 },
  observation: { padding: 12, borderRadius: 10, marginBottom: 8, borderWidth: 1, borderColor: '#e2e8f0' },
  observationSelected: { backgroundColor: '#eff6ff', borderColor: '#93c5fd' },
  observationTime: { color: '#1e40af', fontSize: 14, marginBottom: 6 },
  observationText: { color: '#64748b', fontSize: 17, lineHeight: 26 }, observationTextSelected: { color: '#0f172a', fontWeight: '600' },
  disclosure: { minHeight: 56, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: '#cbd5e1', marginTop: 12 },
  disclosureMark: { color: '#1e40af', fontSize: 14 },
  disclosureTitle: { flex: 1 },
  note: { color: '#475569', fontSize: 15, lineHeight: 23, marginBottom: 12 },
  reviewItem: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' }, reviewLabel: { color: '#0f172a', fontSize: 17, fontWeight: '600', marginBottom: 8 },
  chip: { alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, fontSize: 15, fontWeight: '600', marginBottom: 8 },
  observed: { backgroundColor: '#dbeafe', color: '#1e40af' }, notObserved: { backgroundColor: '#e2e8f0', color: '#334155' }, notAssessable: { backgroundColor: '#fef3c7', color: '#854d0e' },
  details: { paddingTop: 12 }, digest: { color: '#475569', fontSize: 13, lineHeight: 20, marginBottom: 12 },
  deleteButton: { minHeight: 48, padding: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#64748b', borderRadius: 10 }, deleteLabel: { color: '#334155', fontSize: 16 },
  footer: { paddingHorizontal: 16, paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#cbd5e1', backgroundColor: '#ffffff' }, footerButtons: { flexDirection: 'row', gap: 10 },
  shareButton: { flex: 1, minHeight: 52, backgroundColor: '#1d4ed8', padding: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 10 }, shareLabel: { color: '#ffffff', fontSize: 17, fontWeight: '600', textAlign: 'center' },
  newButton: { flex: 1, minHeight: 52, padding: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 10, borderWidth: 1, borderColor: '#94a3b8' }, newLabel: { color: '#334155', fontSize: 17, fontWeight: '600', textAlign: 'center' },
  disabled: { opacity: 0.55 }, shareError: { color: '#9a3412', fontSize: 15, marginBottom: 10 },
})
