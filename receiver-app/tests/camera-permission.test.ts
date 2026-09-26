import assert from 'node:assert/strict'
import test from 'node:test'
import { isCameraPermissionError } from '../src/lib/camera-permission.ts'

test('treats a denied camera prompt as a permission failure', () => {
  assert.equal(isCameraPermissionError(new DOMException('denied', 'NotAllowedError')), true)
  assert.equal(isCameraPermissionError(new DOMException('busy', 'NotReadableError')), false)
  assert.equal(isCameraPermissionError(new Error('denied')), false)
})
