import { useEffect, useRef, useState } from 'react'
import { Image, Modal, Platform, Pressable, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View, useWindowDimensions } from 'react-native'
import { getSystemInsets } from 'dashpi-share'
import { previewForFile } from './preview-model'
import { nearestKeyframe, relativeTimestamp, REVIEW_ITEMS, verifyReportImages, type KeyframeRole, type ValidatedNativeReport } from './native-report'
import { digestReportImage, shareReport } from './share-sheet'
import type { OpticalFile } from './unpack'
import { reviewOverview } from './report-presentation'

const ROLE_LABEL: Record<KeyframeRole, string> = { before: '사고 전', moment: '사고 순간', after: '사고 후' }
const STATUS_LABEL = { observed: '관찰됨', not_observed: '관찰되지 않음', not_determinable: '확인 불가' }

export function localReportTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' })
}

const ICONS = {
  document: require('../assets/report-icons/document.png'), robot: require('../assets/report-icons/robot.png'),
  scales: require('../assets/report-icons/scales.png'), clock: require('../assets/report-icons/clock.png'),
  warning: require('../assets/report-icons/warning.png'), check: require('../assets/report-icons/check.png'),
  back: require('../assets/report-icons/back.png'), chevron: require('../assets/report-icons/chevron.png'),
  download: require('../assets/report-icons/download.png'), refresh: require('../assets/report-icons/refresh.png'),
  expand: require('../assets/report-icons/expand.png'), close: require('../assets/report-icons/close.png'),
  signal: require('../assets/report-icons/signal.png'), road: require('../assets/report-icons/road.png'),
  pedestrian: require('../assets/report-icons/pedestrian.png'), intersection: require('../assets/report-icons/intersection.png'),
} as const

function ReportIcon({ name, color = '#1253e8', size = 24 }: { name: keyof typeof ICONS; color?: string; size?: number }) {
  return <Image source={ICONS[name]} style={{ width: size, height: size, tintColor: color }} accessible={false} />
}

function SectionTitle({ icon, title }: { icon: keyof typeof ICONS; title: string }) {
  return <View style={styles.sectionHeading}><ReportIcon name={icon} /><Text accessibilityRole="header" style={styles.sectionTitle}>{title}</Text></View>
}

function Disclosure({ title, open, toggle }: { title: string; open: boolean; toggle: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={toggle} style={styles.disclosure}>
    <Text style={styles.disclosureTitle}>{title}</Text><Text style={styles.disclosureMark}>{open ? '접기 −' : '펼치기 +'}</Text>
  </Pressable>
}

const REVIEW_PREVIEW = [
  ['signal', '신호 지시', 'signal'], ['crosswalk', '횡단보도 보행자', 'pedestrian'],
  ['center_line', '중앙선 관련', 'road'], ['overtaking', '앞지르기·끼어들기', 'intersection'],
] as const

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
  const scroll = useRef<ScrollView>(null)
  const { width, fontScale } = useWindowDimensions()
  const [photoOpen, setPhotoOpen] = useState(false)
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
  const overview = report ? reviewOverview(report.major_negligence_review) : null
  const showFrame = (role: KeyframeRole) => { setSelected(role); scroll.current?.scrollTo({ y: 0, animated: true }) }
  const image = report?.keyframes.find((frame) => frame.role === selected)
  const safeStyle = Platform.OS === 'android' ? { paddingTop: insets.top, paddingBottom: insets.bottom, paddingLeft: insets.left, paddingRight: insets.right } : undefined

  return <SafeAreaView style={[styles.safe, safeStyle]}>
    <StatusBar barStyle="dark-content" />
    <View style={styles.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="수신 화면으로 돌아가기" onPress={onNewReceive} style={styles.headerBack}><ReportIcon name="back" color="#0b1735" /></Pressable>
      <Text accessibilityRole="header" style={styles.headerTitle}>AI 사고 분석</Text>
      <View style={styles.receiveStatus}>
        <View style={[styles.receiveCheck, !report && styles.pendingCheck]}><ReportIcon name={report ? 'check' : 'clock'} size={14} color="#ffffff" /></View>
        <Text style={[styles.receiveLabel, !report && styles.pendingLabel]}>{preparing ? '검증 중' : report ? '수신 완료' : '확인 필요'}</Text>
      </View>
    </View>
    <ScrollView ref={scroll} style={styles.scroll} contentContainerStyle={styles.content}>
      {preparing ? <Text accessibilityLiveRegion="polite" style={styles.body}>리포트와 이미지 무결성을 검증하고 있습니다.</Text> : null}
      {openError ? <Text accessibilityLiveRegion="polite" style={styles.warning}>{openError}</Text> : null}
      {report && overview ? <>
        {report.keyframes.filter((frame) => frame.imageValid && frame.dataUri).map((frame) => <Image key={`check-${frame.role}`} source={{ uri: frame.dataUri! }} style={styles.decodeCheck} accessible={false} onLoad={() => imageDecoded(frame.role)} onError={() => imageFailed(frame.role)} />)}
        <Text style={styles.recordTime}>{localReportTime(report.triggered_at)}</Text>
        {report.keyframes.some((frame) => !frame.imageValid) ? <Text style={styles.warning}>일부 이미지가 손상되었습니다. 원본 수신 파일은 보관됩니다.</Text> : null}
        <View style={styles.imageBox}>
          {image?.imageValid && image.dataUri ? <Image key={image.role} source={{ uri: image.dataUri }} resizeMode="contain" style={styles.image} accessible accessibilityLabel={`${ROLE_LABEL[selected]} · ${relativeTimestamp(image.timestamp, report.incident_timestamp)}`} onLoad={() => imageDecoded(image.role)} onError={() => imageFailed(image.role)} /> : <Text style={styles.imageError}>이미지 손상 · {ROLE_LABEL[selected]}</Text>}
          {image?.imageValid ? <Pressable accessibilityRole="button" accessibilityLabel="선택한 사진 크게 보기" onPress={() => setPhotoOpen(true)} style={styles.expandPhoto}><ReportIcon name="expand" color="#ffffff" size={22} /></Pressable> : null}
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
        <SectionTitle icon="document" title="AI 요약" />
        <View style={styles.summaryCard}>
          <View style={styles.robotBadge}><ReportIcon name="robot" size={32} /></View>
          <Text style={styles.summaryText}>{report.summary}</Text>
        </View>
        <View style={styles.reviewHeading}>
          <View style={styles.reviewHeadingTitle}><SectionTitle icon="scales" title="12대 중과실 관련 확인" /></View>
          <Pressable accessibilityRole="button" accessibilityLabel={reviewOpen ? '12개 항목 상세 접기' : '12개 항목 상세 펼치기'} accessibilityState={{ expanded: reviewOpen }} onPress={() => setReviewOpen((value) => !value)} style={styles.headingToggle}><ReportIcon name="chevron" color="#506281" size={20} /></Pressable>
        </View>
        <View style={styles.reviewCard}>
          <View style={styles.reviewSummary}>
            <View style={styles.reviewSymbol}><ReportIcon name="scales" color="#ffffff" size={27} /></View>
            <View style={styles.reviewSummaryText}>
              <Text style={styles.reviewTitle}>{overview.title}</Text>
              <Text style={styles.reviewNote}>{overview.detail}</Text>
            </View>
          </View>
          <Text style={styles.legalNote}>법적 판정이 아니라 관련 장면이 보였는지만 정리했습니다.</Text>
          <View style={styles.reviewGrid}>
            {REVIEW_PREVIEW.map(([key, label, icon]) => {
              const entry = report.major_negligence_review[key]
              return <View key={key} style={[styles.reviewPreview, (width < 380 || fontScale > 1.2) && styles.reviewPreviewWide]}>
                <View style={styles.previewIcon}><ReportIcon name={icon} color="#172747" size={23} /></View>
                <View style={styles.previewText}><Text style={styles.previewLabel}>{label}</Text><Text style={[styles.chip, entry.status === 'observed' ? styles.observed : entry.status === 'not_observed' ? styles.notObserved : styles.notAssessable]}>{STATUS_LABEL[entry.status]}</Text></View>
              </View>
            })}
          </View>
          {reviewOpen ? <View style={styles.reviewDetails}>{REVIEW_ITEMS.map(([key, label]) => {
            const entry = report.major_negligence_review[key]
            return <View key={key} style={styles.reviewItem}>
              <Text style={styles.reviewLabel}>{label}</Text>
              <Text style={[styles.chip, entry.status === 'observed' ? styles.observed : entry.status === 'not_observed' ? styles.notObserved : styles.notAssessable]}>{STATUS_LABEL[entry.status]}</Text>
              {entry.evidence ? <Text style={styles.body}>{entry.evidence}</Text> : null}
              {entry.timestamp !== null ? <Pressable accessibilityRole="button" accessibilityLabel={`${label}, 관련 사진 보기`} onPress={() => showFrame(nearestKeyframe(entry.timestamp!, report.keyframes))} style={styles.evidenceLink}><Text style={styles.evidenceLinkLabel}>{relativeTimestamp(entry.timestamp, report.incident_timestamp)} · 관련 사진 보기</Text><ReportIcon name="chevron" size={16} /></Pressable> : null}
            </View>
          })}</View> : null}
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: reviewOpen }} onPress={() => setReviewOpen((value) => !value)} style={styles.reviewAll}><Text style={styles.reviewAllLabel}>{reviewOpen ? '상세 접기' : '12개 항목 모두 보기'}</Text><ReportIcon name="chevron" size={17} /></Pressable>
        </View>
        <SectionTitle icon="clock" title="사고 타임라인" />
        {[...report.observations].sort((a, b) => a.timestamp - b.timestamp).map((observation, index, observations) => {
          const role = nearestKeyframe(observation.timestamp, report.keyframes)
          const active = role === selected
          return <Pressable key={index} accessibilityRole="button" accessibilityLabel={`${relativeTimestamp(observation.timestamp, report.incident_timestamp)}, ${observation.description}, ${ROLE_LABEL[role]} 사진 보기`} accessibilityState={{ selected: active }} onPress={() => showFrame(role)} style={styles.observation}>
            <View style={styles.timelineRail}><View style={styles.timelineDot} />{index < observations.length - 1 ? <View style={styles.timelineLine} /> : null}</View>
            <View style={styles.timelineContent}>
              <View style={styles.timelineTop}><Text style={styles.observationTime}>{relativeTimestamp(observation.timestamp, report.incident_timestamp)}</Text><Text style={styles.photoLink}>{ROLE_LABEL[role]} 사진 ›</Text></View>
              <Text style={[styles.observationText, active && styles.observationTextSelected]}>{observation.description}</Text>
            </View>
          </Pressable>
        })}
        <SectionTitle icon="warning" title="관찰된 관련 장면" />
        <View style={styles.sceneTags}>
          {overview.observed.length ? overview.observed.map(([key, label]) => <View key={key} style={styles.sceneTag}><Text style={styles.sceneTagLabel}>{label}</Text></View>) : <Text style={styles.note}>관찰된 관련 장면이 없습니다. 확인 불가 항목은 별도 확인이 필요합니다.</Text>}
        </View>
        <SectionTitle icon="warning" title="영상 확인의 한계" />
        <View style={styles.limitsCard}>{[...report.limitations, ...report.warnings].map((line, index) => <Text key={index} style={styles.limitText}>• {line}</Text>)}</View>
        <Text style={styles.emergency}>긴급 번호 · 119 구급·소방 · 112 경찰</Text>
        <Text style={styles.storageNote}>대표 이미지 3장과 분석 결과가 앱에 저장됐습니다. 원본 영상은 이 전송에 포함되지 않습니다.</Text>
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
        <Pressable accessibilityRole="button" accessibilityState={{ disabled: preparing || decoding || sharing }} disabled={preparing || decoding || sharing} onPress={() => void share()} style={[styles.shareButton, (preparing || decoding || sharing) && styles.disabled]}><ReportIcon name="download" color="#ffffff" size={20} /><Text style={styles.shareLabel}>{sharing ? '공유 준비 중…' : decoding ? '이미지 확인 중…' : 'PDF 저장·공유'}</Text></Pressable>
        <Pressable accessibilityRole="button" onPress={onNewReceive} style={styles.newButton}><ReportIcon name="refresh" size={20} /><Text style={styles.newLabel}>새로 받기</Text></Pressable>
      </View>
    </View>
    <Modal visible={photoOpen} animationType="fade" onRequestClose={() => setPhotoOpen(false)}>
      <SafeAreaView style={[styles.photoModal, safeStyle]}>
        {photoOpen ? <StatusBar barStyle="light-content" /> : null}
        <View style={styles.photoModalHeader}><Text style={styles.photoModalLabel}>{ROLE_LABEL[selected]}{report && image ? ` · ${relativeTimestamp(image.timestamp, report.incident_timestamp)}` : ''}</Text><Pressable accessibilityRole="button" accessibilityLabel="사진 크게 보기 닫기" onPress={() => setPhotoOpen(false)} style={styles.headerBack}><ReportIcon name="close" color="#ffffff" /></Pressable></View>
        {image?.imageValid && image.dataUri ? <Image source={{ uri: image.dataUri }} resizeMode="contain" style={styles.largePhoto} accessibilityLabel={`${ROLE_LABEL[selected]} 사진`} onError={() => imageFailed(image.role)} /> : <Text style={styles.imageError}>이미지 손상</Text>}
      </SafeAreaView>
    </Modal>
  </SafeAreaView>
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#fafcff' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: '#fafcff' },
  headerBack: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { flex: 1, color: '#0b1735', fontSize: 21, fontWeight: '700', textAlign: 'center' },
  receiveStatus: { flexDirection: 'row', alignItems: 'center', gap: 5 }, receiveCheck: { borderRadius: 12, width: 21, height: 21, backgroundColor: '#61bda6', alignItems: 'center', justifyContent: 'center' },
  receiveLabel: { color: '#13886f', fontSize: 12, fontWeight: '700' }, pendingCheck: { backgroundColor: '#64748b' }, pendingLabel: { color: '#64748b' },
  scroll: { flex: 1 }, content: { padding: 12, paddingTop: 0, paddingBottom: 24, width: '100%', maxWidth: 720, alignSelf: 'center' },
  recordTime: { color: '#667797', fontSize: 12, textAlign: 'right', marginBottom: 8 },
  body: { color: '#172747', fontSize: 15, lineHeight: 23, marginBottom: 10 },
  warning: { color: '#895013', backgroundColor: '#fff4e6', borderRadius: 10, padding: 12, fontSize: 14, lineHeight: 22, marginBottom: 12 },
  imageBox: { backgroundColor: '#142039', borderRadius: 12, overflow: 'hidden', aspectRatio: 16 / 9, justifyContent: 'center', alignItems: 'center' },
  image: { width: '100%', height: '100%' }, imageError: { color: '#ffffff', fontSize: 17, padding: 16 },
  expandPhoto: { position: 'absolute', right: 4, bottom: 4, minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: '#142039aa', borderRadius: 9 },
  decodeCheck: { position: 'absolute', width: 1, height: 1, opacity: 0 },
  tabs: { flexDirection: 'row', gap: 6, marginTop: 8, marginBottom: 8 },
  tab: { flex: 1, minHeight: 58, paddingVertical: 9, paddingHorizontal: 3, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#c7d1e5', borderRadius: 10, backgroundColor: '#fafcff' },
  tabSelected: { backgroundColor: '#1253e8', borderColor: '#1253e8' },
  tabLabel: { color: '#142344', fontSize: 14, fontWeight: '700', textAlign: 'center' },
  tabTime: { color: '#142344', fontSize: 15, fontWeight: '700', marginTop: 3 }, tabLabelSelected: { color: '#ffffff' },
  sectionHeading: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 20, marginBottom: 10 },
  sectionTitle: { flex: 1, color: '#0b1735', fontSize: 19, fontWeight: '700' },
  summaryCard: { flexDirection: 'row', gap: 12, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: '#c5ddff', backgroundColor: '#eff6ff' },
  robotBadge: { backgroundColor: '#d9eaff', width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  summaryText: { flex: 1, color: '#172747', fontSize: 15, lineHeight: 23 },
  reviewHeadingTitle: { flex: 1, minWidth: 0 },
  reviewHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, headingToggle: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 10 },
  reviewCard: { borderWidth: 1, borderColor: '#bad5ff', borderRadius: 13, backgroundColor: '#ffffff', padding: 10 },
  reviewSummary: { flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 10, backgroundColor: '#f0f6ff', padding: 12 },
  reviewSymbol: { width: 47, height: 47, borderRadius: 24, borderWidth: 5, borderColor: '#d4e4ff', backgroundColor: '#397eff', alignItems: 'center', justifyContent: 'center' },
  reviewSummaryText: { flex: 1 }, reviewTitle: { color: '#174cc3', fontSize: 16, fontWeight: '700', lineHeight: 23 }, reviewNote: { color: '#516481', fontSize: 12, lineHeight: 19, marginTop: 4 },
  legalNote: { color: '#617493', fontSize: 12, lineHeight: 19, marginTop: 10 },
  reviewGrid: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4 },
  reviewPreview: { width: '50%', flexDirection: 'row', alignItems: 'center', gap: 7, paddingVertical: 10, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: '#e9eef8' }, reviewPreviewWide: { width: '100%' },
  previewIcon: { width: 32, height: 36, borderRadius: 8, backgroundColor: '#f0f5fd', alignItems: 'center', justifyContent: 'center' }, previewText: { flex: 1 }, previewLabel: { color: '#172747', fontSize: 12, fontWeight: '600', marginBottom: 5 },
  reviewDetails: { paddingTop: 10 }, reviewItem: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#e9eef8' }, reviewLabel: { color: '#172747', fontSize: 15, fontWeight: '600', marginBottom: 8 },
  chip: { alignSelf: 'flex-start', borderRadius: 20, paddingHorizontal: 8, paddingVertical: 4, fontSize: 11, fontWeight: '600' },
  observed: { backgroundColor: '#e9f2ff', color: '#1751ca' }, notObserved: { backgroundColor: '#edf1f7', color: '#536581' }, notAssessable: { backgroundColor: '#fff1df', color: '#995413' },
  evidenceLink: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44 }, evidenceLinkLabel: { color: '#1253e8', fontSize: 13, fontWeight: '600' },
  reviewAll: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', minHeight: 44, marginTop: 10, borderWidth: 1, borderColor: '#c7d1e5', borderRadius: 9 }, reviewAllLabel: { color: '#142344', fontSize: 14, fontWeight: '700' },
  observation: { flexDirection: 'row', gap: 12, minHeight: 65 }, timelineRail: { width: 14, alignItems: 'center', paddingTop: 5 },
  timelineDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#397eff' }, timelineLine: { position: 'absolute', top: 18, bottom: -3, width: 1.5, backgroundColor: '#397eff' },
  timelineContent: { flex: 1, paddingBottom: 17 }, timelineTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 },
  observationTime: { color: '#1253e8', fontSize: 14, fontWeight: '700' }, photoLink: { color: '#667797', fontSize: 11 },
  observationText: { color: '#536581', fontSize: 14, lineHeight: 22 }, observationTextSelected: { color: '#172747', fontWeight: '600' },
  sceneTags: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, sceneTag: { borderRadius: 22, backgroundColor: '#e9eef9', paddingHorizontal: 12, paddingVertical: 8 }, sceneTagLabel: { color: '#172747', fontSize: 12, fontWeight: '600' },
  note: { color: '#536581', fontSize: 13, lineHeight: 21 }, limitsCard: { padding: 12, backgroundColor: '#fff6e9', borderRadius: 12, borderWidth: 1, borderColor: '#f1e0c7' }, limitText: { color: '#805322', fontSize: 13, lineHeight: 21, marginBottom: 5 },
  emergency: { color: '#536581', fontSize: 12, lineHeight: 20, marginTop: 16 }, storageNote: { color: '#667797', fontSize: 12, lineHeight: 20, marginTop: 6 },
  disclosure: { minHeight: 52, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: '#dce4f2', marginTop: 16 }, disclosureMark: { color: '#1253e8', fontSize: 12 }, disclosureTitle: { flex: 1, color: '#172747', fontSize: 15, fontWeight: '600' },
  details: { paddingTop: 12 }, digest: { color: '#536581', fontSize: 12, lineHeight: 19, marginBottom: 12 },
  deleteButton: { minHeight: 48, padding: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#64748b', borderRadius: 10 }, deleteLabel: { color: '#334155', fontSize: 15 },
  footer: { paddingHorizontal: 12, paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#dce4f2', backgroundColor: '#fafcff' }, footerButtons: { flexDirection: 'row', gap: 6 },
  shareButton: { flex: 1.25, flexDirection: 'row', gap: 6, flexWrap: 'wrap', minHeight: 48, backgroundColor: '#1253e8', padding: 10, alignItems: 'center', justifyContent: 'center', borderRadius: 10 }, shareLabel: { color: '#ffffff', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  newButton: { flex: 1, flexDirection: 'row', gap: 6, flexWrap: 'wrap', minHeight: 48, padding: 10, alignItems: 'center', justifyContent: 'center', borderRadius: 10, borderWidth: 1, borderColor: '#1253e8' }, newLabel: { color: '#142344', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  disabled: { opacity: 0.55 }, shareError: { color: '#9a3412', fontSize: 14, marginBottom: 10 },
  photoModal: { flex: 1, backgroundColor: '#101a2e' }, photoModalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12 }, photoModalLabel: { flex: 1, color: '#ffffff', fontSize: 15 }, largePhoto: { flex: 1, width: '100%' },
})
