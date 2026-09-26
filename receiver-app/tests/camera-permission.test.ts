import assert from 'node:assert/strict'
import test from 'node:test'
import { cameraConstraints, isCameraPermissionError } from '../src/lib/camera-permission.ts'

test('requests any camera so the permission prompt is not blocked by a facing-mode constraint', () => {
  assert.deepEqual(cameraConstraints, { audio: false, video: true })
})


test('treats a denied camera prompt as a permission failure', () => {
  assert.equal(isCameraPermissionError(new DOMException('denied', 'NotAllowedError')), true)
  assert.equal(isCameraPermissionError(new DOMException('busy', 'NotReadableError')), false)
  assert.equal(isCameraPermissionError(new Error('denied')), false)
})
