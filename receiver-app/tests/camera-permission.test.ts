import assert from 'node:assert/strict'
import test from 'node:test'
import { cameraSettingsUrl, isCameraPermissionError } from '../src/lib/camera-permission.ts'

test('opens the app settings page for the phone that is running the receiver', () => {
  assert.equal(cameraSettingsUrl('Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X)', 'https://jcmaker.github.io'), 'app-settings:')
  assert.match(
    cameraSettingsUrl('Mozilla/5.0 (Linux; Android 14) Chrome/128.0.0.0 Mobile', 'https://jcmaker.github.io'),
    /package:com\.android\.chrome;end$/,
  )
  assert.match(
    cameraSettingsUrl('Mozilla/5.0 (Linux; Android 14) SamsungBrowser/26.0', 'https://jcmaker.github.io'),
    /package:com\.sec\.android\.app\.sbrowser;end$/,
  )
})

test('treats a denied camera prompt as a permission failure', () => {
  assert.equal(isCameraPermissionError(new DOMException('denied', 'NotAllowedError')), true)
  assert.equal(isCameraPermissionError(new DOMException('busy', 'NotReadableError')), false)
  assert.equal(isCameraPermissionError(new Error('denied')), false)
})
