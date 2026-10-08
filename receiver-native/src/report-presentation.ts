import { REVIEW_ITEMS, type NativeReport } from './native-report.ts'

export function reviewOverview(review: NativeReport['major_negligence_review']) {
  const observed = REVIEW_ITEMS.filter(([key]) => review[key].status === 'observed')
  const unavailable = REVIEW_ITEMS.filter(([key]) => review[key].status === 'not_determinable').length
  return {
    observed,
    unavailable,
    notObserved: REVIEW_ITEMS.length - observed.length - unavailable,
    title: observed.length ? `관련 장면 ${observed.length}개 관찰됨` : unavailable === REVIEW_ITEMS.length ? '영상만으로 확인할 수 없음' : '관찰된 관련 장면 없음',
    detail: unavailable ? `${unavailable}개 항목은 확인 불가 · 추가 확인이 필요합니다.` : '12개 항목의 영상 관찰 결과입니다.',
  }
}
