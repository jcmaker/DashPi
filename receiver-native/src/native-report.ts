export const REPORT_MEDIA_TYPE = 'application/vnd.dashpi.report+json'
export const REPORT_OPEN_FAILED = '리포트를 열 수 없습니다. 원본 파일을 공유하거나 저장할 수 있습니다.'
export const IMAGE_DAMAGED = '이미지 손상'
export const MAX_REPORT_IMAGE_BYTES = 200_000

export const REVIEW_ITEMS = [
  ['signal', '신호 지시 관련 장면'],
  ['center_line', '중앙선 관련 장면'],
  ['speeding', '제한속도 초과 여부'],
  ['overtaking', '앞지르기·끼어들기 관련 장면'],
  ['railroad_crossing', '철길건널목 관련 장면'],
  ['crosswalk', '횡단보도 보행자 관련 장면'],
  ['unlicensed', '운전면허 상태'],
  ['intoxication', '음주·약물 상태'],
  ['sidewalk', '보도 침범 관련 장면'],
  ['passenger_fall', '승객 추락 방지 관련 장면'],
  ['school_zone', '어린이보호구역 관련 장면'],
  ['cargo', '화물 고정 관련 장면'],
] as const

export type ReviewKey = (typeof REVIEW_ITEMS)[number][0]
export type ReviewStatus = 'observed' | 'not_observed' | 'not_determinable'
export type ReviewEntry = { status: ReviewStatus; evidence: string; timestamp: number | null }
export type KeyframeRole = 'before' | 'moment' | 'after'
export type ReportKeyframe = { role: KeyframeRole; timestamp: number; jpeg_base64: string; sha256: string }
export type NativeReport = {
  format: 'dashpi.report'
  version: 1
  incident_id: string
  triggered_at: string
  generated_at: string
  model: string
  incident_timestamp: number
  summary: string
  observations: { timestamp: number; description: string }[]
  limitations: string[]
  major_negligence_review: Record<ReviewKey, ReviewEntry>
  warnings: string[]
  keyframes: ReportKeyframe[]
  digests: { 'clip.mp4': string }
}
export type ValidatedKeyframe = ReportKeyframe & {
  imageValid: boolean
  imageError: string | null
  dataUri: string | null
}
export type ValidatedNativeReport = Omit<NativeReport, 'keyframes'> & { keyframes: ValidatedKeyframe[] }

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid report object')
  return value as Record<string, unknown>
}

function requiredFields(value: Record<string, unknown>, fields: string[]): void {
  if (fields.some((field) => !Object.hasOwn(value, field))) throw new Error('missing report field')
}

function text(value: unknown, nonempty = false): string {
  if (typeof value !== 'string' || (nonempty && !value.trim())) throw new Error('invalid report text')
  return value
}

function timestamp(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error('invalid timestamp')
  return value
}

function digest(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-fA-F0-9]{64}$/.test(value)) throw new Error('invalid digest')
  return value.toLowerCase()
}

function date(value: unknown): string {
  const result = text(value)
  // Require an explicit timezone and reject dates which Date.parse silently normalizes.
  const match = result.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-](\d{2}):(\d{2}))$/)
  if (!match || !Number.isFinite(Date.parse(result))) throw new Error('invalid report date')
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number)
  const calendar = new Date(0)
  calendar.setUTCFullYear(year, month, 0)
  if (month < 1 || month > 12 || day < 1 || day > calendar.getUTCDate() || hour > 23 || minute > 59 || second > 59 ||
      (match[8] !== undefined && (Number(match[8]) > 23 || Number(match[9]) > 59))) {
    throw new Error('invalid report date')
  }
  return result
}

function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error('invalid report array')
  return value
}

function unavailable(evidence = '카메라 영상만으로 확인할 수 없습니다.'): ReviewEntry {
  return { status: 'not_determinable', evidence, timestamp: null }
}

function review(value: unknown): Record<ReviewKey, ReviewEntry> {
  const source = record(value)
  const result = {} as Record<ReviewKey, ReviewEntry>
  for (const [key] of REVIEW_ITEMS) {
    const entry = source[key]
    if (entry === undefined || ['speeding', 'unlicensed', 'intoxication'].includes(key)) {
      result[key] = unavailable()
      continue
    }
    const item = record(entry)
    if (typeof item.status !== 'string' || !['observed', 'not_observed', 'not_determinable'].includes(item.status)) {
      result[key] = unavailable()
      continue
    }
    requiredFields(item, ['status', 'evidence', 'timestamp'])
    result[key] = {
      status: item.status as ReviewStatus,
      evidence: text(item.evidence),
      timestamp: item.timestamp === null ? null : timestamp(item.timestamp),
    }
    if (key === 'school_zone' && result[key].status === 'observed' && !/표지|노면|도로 표시|글자/.test(result[key].evidence)) {
      result[key] = unavailable('어린이보호구역 표지·노면 표시를 영상에서 확인할 수 없습니다.')
    }
  }
  return result
}

/** Validate the JSON structure. Image contents are checked separately and may fail independently. */
export function parseTransferReport(payload: Uint8Array): NativeReport {
  const source = record(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payload)))
  requiredFields(source, ['format', 'version', 'incident_id', 'triggered_at', 'generated_at', 'model',
    'incident_timestamp', 'summary', 'observations', 'limitations', 'major_negligence_review', 'warnings', 'keyframes', 'digests'])
  if (source.format !== 'dashpi.report' || source.version !== 1) throw new Error('unsupported report format')
  const frames = array(source.keyframes)
  if (frames.length !== 3) throw new Error('invalid keyframes count')
  const keyframes = frames.map((entry): ReportKeyframe => {
    const frame = record(entry)
    requiredFields(frame, ['role', 'timestamp', 'jpeg_base64', 'sha256'])
    if (!['before', 'moment', 'after'].includes(String(frame.role))) throw new Error('invalid keyframe role')
    return { role: frame.role as KeyframeRole, timestamp: timestamp(frame.timestamp),
      jpeg_base64: text(frame.jpeg_base64), sha256: digest(frame.sha256) }
  })
  if (new Set(keyframes.map((frame) => frame.role)).size !== 3) throw new Error('duplicate keyframe role')
  const digests = record(source.digests)
  requiredFields(digests, ['clip.mp4'])
  return {
    format: 'dashpi.report', version: 1,
    incident_id: text(source.incident_id, true), triggered_at: date(source.triggered_at), generated_at: date(source.generated_at),
    model: text(source.model, true), incident_timestamp: timestamp(source.incident_timestamp), summary: text(source.summary),
    observations: array(source.observations).map((entry) => {
      const item = record(entry)
      requiredFields(item, ['timestamp', 'description'])
      return { timestamp: timestamp(item.timestamp), description: text(item.description) }
    }),
    limitations: array(source.limitations).map((item) => text(item)),
    major_negligence_review: review(source.major_negligence_review),
    warnings: array(source.warnings).map((item) => text(item)), keyframes,
    digests: { 'clip.mp4': digest(digests['clip.mp4']) },
  }
}

function imageBytes(value: string): Uint8Array {
  // Reject excess size before allocating a decoded image, including any padded excess.
  if (!value || value.length > 4 * Math.ceil(MAX_REPORT_IMAGE_BYTES / 3) ||
      value.length % 4 !== 0 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw new Error(IMAGE_DAMAGED)
  }
  const binary = atob(value)
  if (binary.length > MAX_REPORT_IMAGE_BYTES || binary.length < 2 || binary.charCodeAt(0) !== 0xff || binary.charCodeAt(1) !== 0xd8 || btoa(binary) !== value) {
    throw new Error(IMAGE_DAMAGED)
  }
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

export async function verifyReportImages(
  report: NativeReport,
  sha256: (bytes: Uint8Array) => Promise<string>,
): Promise<ValidatedNativeReport> {
  const keyframes = await Promise.all(report.keyframes.map(async (frame): Promise<ValidatedKeyframe> => {
    try {
      const bytes = imageBytes(frame.jpeg_base64)
      if ((await sha256(bytes)).toLowerCase() !== frame.sha256) throw new Error(IMAGE_DAMAGED)
      return { ...frame, imageValid: true, imageError: null, dataUri: `data:image/jpeg;base64,${frame.jpeg_base64}` }
    } catch {
      return { ...frame, imageValid: false, imageError: IMAGE_DAMAGED, dataUri: null }
    }
  }))
  return { ...report, keyframes }
}

export function relativeTimestamp(value: number, incidentTimestamp: number): string {
  const difference = value - incidentTimestamp
  const rounded = Number(difference.toFixed(1))
  return `${rounded > 0 ? '+' : ''}${rounded === 0 ? '0.0' : rounded.toFixed(1)}초`
}

export function nearestKeyframe(value: number, keyframes: readonly Pick<ReportKeyframe, 'role' | 'timestamp'>[]): KeyframeRole {
  if (!keyframes.length) throw new Error('no keyframes')
  const roles: Record<KeyframeRole, number> = { moment: 0, before: 1, after: 2 }
  return [...keyframes].sort((left, right) => {
    const distance = Math.abs(left.timestamp - value) - Math.abs(right.timestamp - value)
    if (distance !== 0) return distance
    if (left.role === 'moment' || right.role === 'moment') return roles[left.role] - roles[right.role]
    return left.timestamp - right.timestamp || roles[left.role] - roles[right.role]
  })[0].role
}
