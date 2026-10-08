import { IMAGE_DAMAGED, REVIEW_ITEMS, relativeTimestamp } from './native-report.ts'
import type { ReviewStatus, ValidatedNativeReport } from './native-report.ts'

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
}

const STATUS_LABELS: Record<ReviewStatus, string> = {
  observed: '관찰됨', not_observed: '관찰되지 않음', not_determinable: '확인 불가',
}
const ROLE_LABELS = { before: '사고 전', moment: '사고 순간', after: '사고 후' }

/** A single offline document, using only image bytes which passed verification. */
export function renderReportHtml(report: ValidatedNativeReport): string {
  const relative = (value: number) => relativeTimestamp(value, report.incident_timestamp)
  const figures = ['before', 'moment', 'after'].map((role) => {
    const frame = report.keyframes.find((entry) => entry.role === role)!
    const label = ROLE_LABELS[frame.role]
    const content = frame.imageValid && frame.dataUri !== null
      ? `<img src="${escapeHtml(frame.dataUri)}" alt="${label}">`
      : `<p class="damaged">${IMAGE_DAMAGED}</p>`
    return `<figure>${content}<figcaption>${label} · ${relative(frame.timestamp)}</figcaption></figure>`
  }).join('')
  const observations = [...report.observations].sort((left, right) => left.timestamp - right.timestamp)
    .map((entry) => `<li><time>${relative(entry.timestamp)}</time><span>${escapeHtml(entry.description)}</span></li>`).join('')
  const limits = [...report.limitations, ...report.warnings].map((entry) => `<li>${escapeHtml(entry)}</li>`).join('')
  const review = REVIEW_ITEMS.map(([key, label]) => {
    const entry = report.major_negligence_review[key]
    return `<li><strong>${label}</strong><span class="status ${entry.status}">${STATUS_LABELS[entry.status]}</span>` +
      `<p>${escapeHtml(entry.evidence)}${entry.timestamp === null ? '' : ` · ${relative(entry.timestamp)}`}</p></li>`
  }).join('')
  const digests = report.keyframes.map((frame) => `<dt>${ROLE_LABELS[frame.role]} SHA-256</dt><dd>${escapeHtml(frame.sha256)}</dd>`).join('')
  const integrity = report.keyframes.every((frame) => frame.imageValid) ? '무결성 검증 완료' : '일부 이미지 손상'
  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DashPi 사고 분석 리포트</title><style>
*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#182334;font:16px/1.6 system-ui,sans-serif}main{max-width:960px;margin:auto;padding:20px}section,header,details{background:white;border-radius:16px;padding:20px;margin:0 0 16px}h1,h2{line-height:1.3}h1{font-size:26px}h2,summary{font-size:20px}p,li,dd{overflow-wrap:anywhere;white-space:pre-wrap}.scenes{display:flex;flex-wrap:wrap;gap:12px}figure{flex:1 1 230px;margin:0}img{display:block;width:100%;height:auto;border-radius:10px}figcaption{padding:8px 0}ul{padding-left:22px}li{margin:10px 0}time{font-weight:600;margin-right:12px}.status{display:inline-block;margin:6px 10px;padding:2px 10px;border-radius:20px;font-size:14px}.observed{color:#1749a0;background:#e8f0ff}.not_observed{color:#424b57;background:#edf0f3}.not_determinable{color:#785000;background:#fff1cf}.damaged{background:#edf0f3;min-height:140px;display:grid;place-items:center}dd{margin:0 0 12px;font-family:monospace;font-size:14px}dt{font-weight:600}summary{cursor:pointer;font-weight:600}details>p{margin-top:16px}@media(max-width:600px){main{padding:12px}section,header,details{padding:16px}}@media print{body{background:white}section,header,details{break-inside:avoid}}
</style></head><body><main>
<header><h1>사고 분석 리포트</h1><p>${escapeHtml(new Date(report.triggered_at).toLocaleString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' }))}</p><p>${integrity}</p></header>
<section aria-label="대표 이미지"><div class="scenes">${figures}</div></section>
<section><h2>AI 요약</h2><p>${escapeHtml(report.summary)}</p></section>
<section><h2>시간별 관찰</h2><ul>${observations}</ul></section>
<section><h2>영상으로 확인할 수 없는 내용</h2><ul>${limits}</ul></section>
<details><summary>12대 중과실 관련 영상 확인</summary><p>법적 판정이 아니라 관련 장면이 보였는지만 정리했습니다.</p><ul>${review}</ul></details>
<section><h2>긴급 번호</h2><p>119 구급·소방</p><p>112 경찰</p></section>
<details><summary>증거 상세</summary><dl><dt>사고 ID</dt><dd>${escapeHtml(report.incident_id)}</dd><dt>생성 시각</dt><dd>${escapeHtml(report.generated_at)}</dd><dt>모델</dt><dd>${escapeHtml(report.model)}</dd><dt>원본 클립 SHA-256</dt><dd>${escapeHtml(report.digests['clip.mp4'])}</dd>${digests}</dl></details>
</main></body></html>`
}
