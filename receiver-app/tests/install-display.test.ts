import assert from 'node:assert/strict'
import test from 'node:test'
import { isInstalledDisplay } from '../src/hooks/use-install-prompt.ts'

test('treats a home-screen launch as the installed app', () => {
  const browser = () => false
  assert.equal(isInstalledDisplay(browser, false), false)
  assert.equal(isInstalledDisplay((query) => query.includes('standalone'), false), true)
  assert.equal(isInstalledDisplay(browser, true), true)
})
