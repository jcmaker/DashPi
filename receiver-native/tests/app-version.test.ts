import assert from 'node:assert/strict'
import test from 'node:test'
import { versionCode } from '../scripts/set-app-version.mjs'

test('versionCode grows with every release so Android accepts the update', () => {
  assert.equal(versionCode('1.0.0'), 10000)
  assert.equal(versionCode('1.0.1'), 10001)
  assert.ok(versionCode('1.10.0') > versionCode('1.9.99'))
  assert.ok(versionCode('2.0.0') > versionCode('1.99.99'))
})

test('rejects versions it cannot order', () => {
  assert.throws(() => versionCode('1.2'), /MAJOR.MINOR.PATCH/)
  assert.throws(() => versionCode('1.100.0'), /0-99/)
})
