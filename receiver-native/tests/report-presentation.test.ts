import assert from 'node:assert/strict'
import test from 'node:test'
import { REVIEW_ITEMS, type NativeReport } from '../src/native-report.ts'
import { reviewOverview } from '../src/report-presentation.ts'

const review = (status: 'observed' | 'not_observed' | 'not_determinable') =>
  Object.fromEntries(REVIEW_ITEMS.map(([key]) => [key, { status, evidence: '', timestamp: null }])) as NativeReport['major_negligence_review']

test('unknown items remain visible even when no related scene was observed', () => {
  const value = review('not_observed')
  value.speeding.status = value.unlicensed.status = value.intoxication.status = 'not_determinable'
  const result = reviewOverview(value)
  assert.equal(result.observed.length, 0)
  assert.equal(result.unavailable, 3)
  assert.equal(result.notObserved, 9)
  assert.match(result.detail, /3개 항목은 확인 불가/)
  assert.doesNotMatch(result.title, /중과실.*없|위반.*없|안전/)
})

test('scene tags contain only observed items and follow the fixed checklist order', () => {
  const value = review('not_determinable')
  value.crosswalk.status = value.signal.status = 'observed'
  const result = reviewOverview(value)
  assert.deepEqual(result.observed.map(([key]) => key), ['signal', 'crosswalk'])
  assert.equal(result.unavailable, 10)
  assert.equal(result.notObserved, 0)
  assert.match(result.title, /2개/)
})

test('a legacy report with no assessable checklist never implies all items were checked', () => {
  const result = reviewOverview(review('not_determinable'))
  assert.equal(result.title, '영상만으로 확인할 수 없음')
  assert.equal(result.unavailable, 12)
  assert.equal(result.notObserved, 0)
})
