import assert from 'node:assert/strict'
import test from 'node:test'
import { cameraGate } from '../src/camera-gate.ts'

test('asks for the camera until it is granted, on either platform', () => {
  assert.equal(cameraGate(null), 'checking')
  assert.equal(cameraGate({ granted: false, canAskAgain: true }), 'request')
  assert.equal(cameraGate({ granted: false, canAskAgain: false }), 'settings')
  assert.equal(cameraGate({ granted: true, canAskAgain: false }), 'scan')
})
