import assert from 'node:assert/strict'
import test from 'node:test'
import { isInstalledDisplay } from '../src/hooks/use-install-prompt.ts'

test('treats a home-screen launch as the installed app', () => {
  const browser = (query: string) => query.includes('browser')
  assert.equal(isInstalledDisplay(browser, false), false)
  assert.equal(isInstalledDisplay((query) => query.includes('standalone'), false), true)
  assert.equal(isInstalledDisplay(browser, true), false)
})

test('keeps a normal mobile browser on the install screen', () => {
  assert.equal(isInstalledDisplay((query) => query.includes('minimal-ui'), false), false)
  assert.equal(isInstalledDisplay((query) => query.includes('fullscreen'), false), false)
})
