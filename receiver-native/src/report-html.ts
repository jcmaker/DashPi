import { IMAGE_DAMAGED, REVIEW_ITEMS, relativeTimestamp } from './native-report.ts'
import { reviewOverview } from './report-presentation.ts'
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
  const overview = reviewOverview(report.major_negligence_review)
  const tags = overview.observed.map(([, label]) => `<span class="scene-tag">${escapeHtml(label)}</span>`).join('')
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
*{box-sizing:border-box}body{margin:0;background:#fafcff;color:#172747;font:15px/1.6 system-ui,sans-serif}main{max-width:720px;margin:auto;padding:16px}header{margin-bottom:16px;text-align:center}h1{font-size:23px;color:#0b1735;margin:6px 0}h2,summary{font-size:19px;color:#0b1735;font-weight:700}h2{margin:22px 0 10px}p,li,dd{overflow-wrap:anywhere;white-space:pre-wrap}.record-time{color:#667797;font-size:12px}.integrity{color:#13886f;font-size:13px}.scenes{display:flex;flex-wrap:wrap;gap:10px}figure{flex:1 1 200px;margin:0}img{display:block;width:100%;height:auto;border-radius:12px}figcaption{text-align:center;border:1px solid #c7d1e5;border-radius:10px;padding:10px;margin-top:8px;font-weight:700}.summary-card{padding:16px;border:1px solid #c5ddff;border-radius:12px;background:#eff6ff}.summary-card p{margin:0}.review-card{padding:12px;border:1px solid #bad5ff;border-radius:13px;background:white}.overview{padding:14px;background:#f0f6ff;border-radius:10px}.overview strong{font-size:17px;color:#174cc3}.overview p,.legal-note{font-size:13px;color:#617493;margin:6px 0}.review-card summary{font-size:14px;cursor:pointer;padding:10px;border:1px solid #c7d1e5;border-radius:9px;margin-top:12px}.review-card ul{list-style:none;padding:0}.review-card li{border-bottom:1px solid #e9eef8;padding:12px 0}.timeline{list-style:none;padding:0 0 0 20px}.timeline li{position:relative;border-left:2px solid #397eff;padding:0 0 18px 20px;margin-left:-15px}.timeline li:last-child{border-color:transparent}.timeline li:before{content:"";position:absolute;left:-6px;top:7px;width:10px;height:10px;background:#397eff;border-radius:50%}time{display:block;color:#1253e8;font-size:14px;font-weight:700}.status{display:inline-block;margin:6px 8px;padding:3px 9px;border-radius:20px;font-size:12px}.observed{color:#1751ca;background:#e9f2ff}.not_observed{color:#536581;background:#edf1f7}.not_determinable{color:#995413;background:#fff1df}.scene-tags{display:flex;flex-wrap:wrap;gap:8px}.scene-tag{border-radius:22px;background:#e9eef9;padding:8px 12px;font-size:13px}.limits{border:1px solid #f1e0c7;border-radius:12px;padding:12px;background:#fff6e9;color:#805322}.limits ul{padding-left:20px;margin:0}.damaged{background:#edf1f7;min-height:140px;display:grid;place-items:center}.emergency,.storage-note{font-size:12px;color:#667797}.evidence{border-top:1px solid #dce4f2;margin-top:20px;padding-top:12px}dd{margin:0 0 12px;font:12px/1.6 monospace}dt{font-weight:600}summary{cursor:pointer}details>p{margin-top:16px}@media(max-width:600px){main{padding:12px}}@media print{body{background:white}section,figure,.review-card{break-inside:avoid}}

</style></head><body><main>
<header><h1>AI 사고 분석</h1><p class="record-time">${escapeHtml(new Date(report.triggered_at).toLocaleString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' }))}</p><p class="integrity">${integrity}</p></header>
<section aria-label="대표 이미지"><div class="scenes">${figures}</div></section>
<section><h2>AI 요약</h2><div class="summary-card"><p>${escapeHtml(report.summary)}</p></div></section>
<section><h2>12대 중과실 관련 확인</h2><div class="review-card"><div class="overview"><strong>${escapeHtml(overview.title)}</strong><p>${escapeHtml(overview.detail)}</p></div><p class="legal-note">법적 판정이 아니라 관련 장면이 보였는지만 정리했습니다.</p><details><summary>12개 항목 모두 보기</summary><ul>${review}</ul></details></div></section>
<section><h2>사고 타임라인</h2><ul class="timeline">${observations}</ul></section>
<section><h2>관찰된 관련 장면</h2><div class="scene-tags">${tags || '<p>관찰된 관련 장면이 없습니다. 확인 불가 항목은 별도 확인이 필요합니다.</p>'}</div></section>
<section><h2>영상 확인의 한계</h2><div class="limits"><ul>${limits}</ul></div></section>
<p class="emergency">긴급 번호 · 119 구급·소방 · 112 경찰</p>
<p class="storage-note">대표 이미지 3장과 분석 결과를 담았습니다. 원본 영상은 이 파일에 포함되지 않습니다.</p>
<details class="evidence"><summary>증거 상세</summary><dl><dt>사고 ID</dt><dd>${escapeHtml(report.incident_id)}</dd><dt>생성 시각</dt><dd>${escapeHtml(report.generated_at)}</dd><dt>모델</dt><dd>${escapeHtml(report.model)}</dd><dt>원본 클립 SHA-256</dt><dd>${escapeHtml(report.digests['clip.mp4'])}</dd>${digests}</dl></details>
</main></body></html>`
}
