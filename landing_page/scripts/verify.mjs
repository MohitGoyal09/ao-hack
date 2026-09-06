import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const APP_URL = process.env.APP_URL || 'http://localhost:4173'
const PORT = 9224
const EXTRA_FLAGS = (process.env.CH_TEST_FLAGS || '--enable-unsafe-swiftshader').split(' ')

const chrome = spawn(
  CHROME,
  [
    '--headless=new',
    '--no-sandbox',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + path.join(__dirname, '..', '.chrome-verify'),
    '--window-size=1440,900',
    ...EXTRA_FLAGS,
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
      errors.push('EXCEPTION: ' + JSON.stringify(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text))
    } else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
      errors.push('LOG: ' + msg.params.entry.text)
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
  await send('Page.navigate', { url: APP_URL })
  await sleep(10000)

  const evalRes = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      rootHtmlLen: (document.querySelector('#root')?.innerHTML || '').length,
      title: document.title,
      hasHero: !!document.querySelector('.hero-title'),
      heroText: document.querySelector('.hero-title')?.innerText || '',
      canvases: document.querySelectorAll('canvas').length,
      hasMarquee: !!document.querySelector('.marquee'),
      hasEngineCards: document.querySelectorAll('.card').length,
      hasWorkflowSteps: document.querySelectorAll('.step').length,
      hasGuarantees: document.querySelectorAll('.guarantee').length,
      hasStatus: !!document.querySelector('.status-card'),
      hasFooter: !!document.querySelector('.footer'),
      webglFallback: !!document.querySelector('.webgl-fallback'),
      fallbackCount: document.querySelectorAll('.webgl-fallback').length,
      heroSceneHtml: (document.querySelector('.hero-scene')?.innerHTML || '').slice(0, 900),
      webglError: window.__ruxWebGLError || 'n/a',
      webgl2: !!document.createElement('canvas').getContext('webgl2'),
      webgl1: !!document.createElement('canvas').getContext('webgl'),
      attrsHi: (() => {
        const c = document.createElement('canvas');
        return !!c.getContext('webgl2', { antialias: true, alpha: true, powerPreference: 'high-performance' });
      })(),
      attrsLo: (() => {
        const c = document.createElement('canvas');
        return !!c.getContext('webgl2', { antialias: true, alpha: true });
      })(),
      bodyTextLen: document.body.innerText.length
    })`,
    returnByValue: true,
  })

  console.log('=== RESULT ===')
  console.log(evalRes.result.result.value)
  console.log('=== JS ERRORS ===')
  console.log(errors.length ? errors.join('\n') : 'none')
} catch (e) {
  console.error('CDP failed:', e && e.message)
} finally {
  chrome.kill()
  process.exit(0)
}