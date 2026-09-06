import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const APP_URL = process.env.APP_URL || 'http://localhost:4173'
const OUT = path.join(__dirname, '..', 'screenshots')
const PORT = 9225

fs.mkdirSync(OUT, { recursive: true })
for (const f of fs.readdirSync(OUT)) fs.rmSync(path.join(OUT, f), { force: true })

const chrome = spawn(
  CHROME,
  [
    '--headless=new',
    '--no-sandbox',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + path.join(__dirname, '..', '.chrome-shot'),
    '--enable-unsafe-swiftshader',
    '--window-size=1440,2000',
    '--hide-scrollbars',
    'about:blank',
  ],
  { stdio: 'ignore' }
)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let ws
const pending = new Map()
const errors = []
let id = 0

try {
  await sleep(2000)
  const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()
  const page = targets.find((t) => t.type === 'page')
  ws = new WebSocket(page.webSocketDebuggerUrl)

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg)
      pending.delete(msg.id)
    } else if (msg.method === 'Runtime.exceptionThrown') {
      errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
    } else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
      errors.push(msg.params.entry.text)
    }
  }

  const send = (method, params = {}) =>
    new Promise((resolve) => {
      const mid = ++id
      pending.set(mid, resolve)
      ws.send(JSON.stringify({ id: mid, method, params }))
    })

  await new Promise((res) => (ws.onopen = res))
  await send('Runtime.enable')
  await send('Page.enable')
  await send('Log.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 2000,
    deviceScaleFactor: 1.5,
    mobile: false,
  })
  await send('Page.navigate', { url: APP_URL })
  await sleep(9000)

  const shot = async (name) => {
    const { result } = await send('Page.captureScreenshot', { format: 'png', fromSurface: true })
    const file = path.join(OUT, name + '.png')
    fs.writeFileSync(file, Buffer.from(result.data, 'base64'))
    console.log('saved', name + '.png')
  }

  // sections are large, so use full-page screenshots at progressive scroll positions
  await send('Runtime.evaluate', { expression: 'window.scrollTo(0, 0)' })
  await sleep(2500)
  await shot('1-hero')

  await send('Runtime.evaluate', { expression: 'window.scrollTo(0, window.innerHeight * 0.86)' })
  await sleep(2200)
  await shot('2-marquee-start')

  await send('Runtime.evaluate', { expression: 'window.scrollTo({top: document.querySelector("#engine").offsetTop - 40, behavior: "instant"})' })
  await sleep(2500)
  await shot('3-engine')

  await send('Runtime.evaluate', { expression: 'window.scrollTo({top: document.querySelector("#workflow").offsetTop - 40, behavior: "instant"})' })
  await sleep(2500)
  await shot('4-workflow')

  await send('Runtime.evaluate', { expression: 'window.scrollTo({top: document.querySelector("#review").offsetTop - 40, behavior: "instant"})' })
  await sleep(2500)
  await shot('5-human-loop')

  await send('Runtime.evaluate', { expression: 'window.scrollTo({top: document.querySelector("#status").offsetTop - 40, behavior: "instant"})' })
  await sleep(2600)
  await shot('6-status')

  await send('Runtime.evaluate', { expression: 'window.scrollTo(0, document.body.scrollHeight)' })
  await sleep(2200)
  await shot('7-footer')

  // full-page tall capture
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: Math.min(12000, await (await send('Runtime.evaluate', { expression: 'document.body.scrollHeight', returnByValue: true })).result.result.value),
    deviceScaleFactor: 1,
    mobile: false,
  })
  await sleep(1500)
  await shot('8-full-page')

  const evalRes = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      scrollHeight: document.body.scrollHeight,
      canvases: document.querySelectorAll('canvas').length,
      webglActive: !!document.querySelector('canvas[data-engine]'),
      sections: ['engine','workflow','review','status'].every(id => !!document.getElementById(id)),
      bodyTextLen: document.body.innerText.length
    })`,
    returnByValue: true,
  })
  console.log('=== PAGE STATE ===')
  console.log(evalRes.result.result.value)
  console.log('=== JS ERRORS ===')
  console.log(errors.length ? errors.join('\n') : 'none')
} catch (e) {
  console.error('screenshot run failed:', e && e.message)
  process.exitCode = 1
} finally {
  chrome.kill()
  process.exit(process.exitCode || 0)
}