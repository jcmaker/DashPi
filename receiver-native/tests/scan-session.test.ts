import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FRAME_STALL_MS,
  STALL_MESSAGE,
  isFreshFrame,
  messageForFrameError,
  offerDiscard,
  screenShouldStayAwake,
  stallMessage,
} from '../src/scan-session.ts'

const start = 1_000_000

test('keeps the screen awake only while scanning, receiving, or verifying', () => {
  assert.equal(screenShouldStayAwake('scanning'), true)
  assert.equal(screenShouldStayAwake('receiving'), true)
  assert.equal(screenShouldStayAwake('verifying'), true)
  assert.equal(screenShouldStayAwake('verified'), false)
})

test('offers discard during an in-progress collection and after a visible error', () => {
  assert.equal(offerDiscard('scanning'), false)
  assert.equal(offerDiscard('receiving'), true)
  assert.equal(offerDiscard('verifying'), true)
  assert.equal(offerDiscard('scanning', '받은 데이터를 열 수 없습니다.'), true)
  assert.equal(offerDiscard('verified'), false)
  assert.equal(offerDiscard('verified', STALL_MESSAGE), false)
})

test('surfaces unrecoverable frame errors and treats CRC corruption as noise', () => {
  assert.equal(FRAME_STALL_MS, 8_000)
  assert.equal(messageForFrameError(new Error('crc mismatch')), undefined)
  assert.equal(messageForFrameError(new Error('foreign frame')), undefined)
  assert.equal(messageForFrameError(new Error('malformed frame')), undefined)
  assert.equal(
    messageForFrameError(new Error('unsupported protocol')),
    '이 송신 형식을 읽으려면 수신기를 업데이트하세요.',
  )
  assert.equal(
    messageForFrameError(new Error('conflicting equation')),
    '수신한 QR이 서로 맞지 않습니다. 새로 받으세요.',
  )
})

test('reports a stall only after the receive interval with no fresh frame', () => {
  assert.equal(stallMessage('scanning', start, start + FRAME_STALL_MS), undefined)
  assert.equal(stallMessage('verifying', start, start + FRAME_STALL_MS), undefined)
  assert.equal(stallMessage('verified', start, start + FRAME_STALL_MS), undefined)
  assert.equal(stallMessage('receiving', null, start + FRAME_STALL_MS), undefined)
  assert.equal(stallMessage('receiving', start, start + FRAME_STALL_MS - 1), undefined)
  assert.equal(stallMessage('receiving', start, start + FRAME_STALL_MS), STALL_MESSAGE)
})

test('treats a repeated QR as the same frame and a new sequence as progress', () => {
  assert.equal(isFreshFrame(null, { sessionId: 1, sequence: 4 }), true)
  assert.equal(isFreshFrame({ sessionId: 1, sequence: 4 }, { sessionId: 1, sequence: 4 }), false)
  assert.equal(isFreshFrame({ sessionId: 1, sequence: 4 }, { sessionId: 1, sequence: 5 }), true)
  assert.equal(isFreshFrame({ sessionId: 1, sequence: 4 }, { sessionId: 2, sequence: 4 }), true)
})
