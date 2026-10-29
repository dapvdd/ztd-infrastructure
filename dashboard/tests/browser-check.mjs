// Isolated synthetic API fixtures only; never contacts production.
// Set PLAYWRIGHT_MODULE to the installed playwright entry point.
import { pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href)
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))
const device = { id: 'test-device', hostname: 'Isolated test device', status: 'ONLINE', modules: ['test-module'], last_seen: '2026-10-29T10:00:00Z' }
let mode = 'normal'
let releaseDevices
let logRequests = 0
await page.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/logs')) logRequests++
  if (mode === 'slow-devices' && path.endsWith('/devices')) await new Promise(resolve => { releaseDevices = resolve })
  let body = []
  let status = 200
  if (path.endsWith('/missing')) { status = 404; body = { detail: 'Not found' } }
  else if (path.endsWith('/summary')) body = { total_devices: 1, online_devices: 1, offline_devices: 0, rooms_count: 0 }
  else if (path.endsWith('/devices')) body = [device]
  else if (path.endsWith('/test-device')) body = device
  else if (path.endsWith('/metrics')) body = { available: false }
  else if (path.endsWith('/modules')) { status = 503; body = { detail: 'Catalog unavailable' } }
  if (mode === 'error' && path.endsWith('/telemetry')) { status = 500; body = { detail: 'Telemetry unavailable' } }
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
})
try {
  await page.goto('http://127.0.0.1:4175/devices/test-device')
  await page.getByRole('heading', { name: 'Isolated test device' }).waitFor()
  await page.getByText('No telemetry reported.', { exact: true }).waitFor()
  await page.getByRole('link', { name: 'Configure modules for this device' }).click()
  await page.getByText(/Repository catalog unavailable/).waitFor()
  assert.equal(await page.locator('select').first().inputValue(), 'test-device')
  await page.getByRole('button', { name: 'Refresh data', exact: true }).waitFor()
  const initialLogs = logRequests
  mode = 'slow-devices'
  const deviceRequest = page.waitForRequest('**/api/v1/devices')
  await page.getByRole('button', { name: 'Refresh data', exact: true }).click()
  await deviceRequest
  assert.equal(logRequests, initialLogs, 'History must wait for device validation')
  assert.equal(await page.locator('select').first().isDisabled(), true)
  await page.waitForFunction(() => document.querySelector('select')?.disabled)
  assert.ok(releaseDevices)
  mode = 'normal'
  releaseDevices()
  await page.getByRole('button', { name: 'Refresh data', exact: true }).waitFor()
  await page.waitForFunction(() => !document.querySelector('select')?.disabled)
  assert.equal(logRequests, initialLogs + 1, 'Refresh loads history exactly once')
  await page.goto('http://127.0.0.1:4175/devices/missing')
  await page.getByRole('heading', { name: 'Device not found' }).waitFor()
  assert.equal(await page.getByRole('link', { name: 'Configure modules for this device' }).count(), 0)
  mode = 'error'
  await page.goto('http://127.0.0.1:4175/devices/test-device')
  await page.getByText(/Could not load telemetry:/).waitFor()
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow at ${width}`)
  }
  await page.keyboard.press('Tab')
  assert.ok(await page.evaluate(() => document.activeElement !== document.body))
  for (const path of ['/', '/deployments', '/login', '/users', '/infrastructure']) {
    await page.goto(`http://127.0.0.1:4175${path}`)
    await page.locator('h2').first().waitFor()
  }
  assert.deepEqual(errors, [])
  console.log('PASS: isolated browser routing, device identity/404, empty/error states, catalog failure, device action target, responsive widths, keyboard focus, no uncaught page errors.')
} finally { await browser.close() }
