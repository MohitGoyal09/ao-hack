import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/**
 * Kinetic Type — a word tiled over a 3D solid and dragged around it by the clock.
 * Port of the Codrops Kinetic Typography demo in Green & Cream palette for Rux.
 */

const CAM_DISTANCE = 50
const SPAN = 2 * Math.tan((45 * Math.PI) / 180 / 2) * CAM_DISTANCE
const TILE_W = 1024
const TILE_H = 576
const FILL_W = 0.92

const SHAPES = {
  torusKnot: { repeat: [12, 3] },
  box: { repeat: [3, 3] },
}

const DEFAULTS = {
  shape: 'torusKnot',
  word: 'RUX · AUTONOMOUS COVENANT ENGINE · REVISION LOCK · SAFE-PYTHON ·',
  color: '#f7f5ec', // Cream
  fill: '#0e5b56',  // Pine Green
  fogColor: '#092c25', // Deep Obsidian Green
  density: 12,
  speed: 10,
  distort: 8,
  sizePercent: 102,
  hoverBoost: 8,
  font: {
    fontFamily: 'Albert Sans, Impact, system-ui, sans-serif',
    fontSize: 62,
    fontWeight: 900,
    fontStyle: 'normal',
    letterSpacing: 1,
  },
}

function clamp(v, lo, hi, fallback) {
  const n = typeof v === 'number' && isFinite(v) ? v : fallback
  return Math.max(lo, Math.min(hi, n))
}

function toPx(v, fallback, emBasis) {
  if (typeof v === 'number' && isFinite(v)) return v
  if (typeof v === 'string') {
    const n = parseFloat(v)
    if (!isFinite(n)) return fallback
    if (v.indexOf('em') >= 0) return n * emBasis
    if (v.indexOf('%') >= 0) return (n / 100) * emBasis
    return n
  }
  return fallback
}

function settingsFor(cfg) {
  const shape = SHAPES[cfg.shape] ? cfg.shape : DEFAULTS.shape
  const base = SHAPES[shape].repeat
  const font = cfg.font || DEFAULTS.font
  const heightPct = clamp(toPx(font.fontSize, 62, 100), 10, 300, 62)
  const d = clamp(cfg.density, 1, 20, DEFAULTS.density) / 10

  return {
    shape,
    family: font.fontFamily || DEFAULTS.font.fontFamily,
    weight: font.fontWeight || 900,
    fontStyle: font.fontStyle || 'normal',
    tracking: toPx(font.letterSpacing, 1, 1) * 2,
    capHeight: (heightPct / 100) * TILE_H,
    repeat: [
      Math.max(1, Math.round(base[0] * d)),
      Math.max(1, Math.round(base[1] * d)),
    ],
    speed: clamp(cfg.speed, 0, 20, DEFAULTS.speed) / 10,
    distort: clamp(cfg.distort, 0, 20, DEFAULTS.distort) / 10,
    hoverBoost: clamp(cfg.hoverBoost, 0, 20, DEFAULTS.hoverBoost) * 0.35,
    zoom: 100 / clamp(cfg.sizePercent, 20, 200, DEFAULTS.sizePercent),
  }
}

const VERTEX = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vPosition;

  uniform float uTime;
  uniform float uDistort;

  mat4 rotation3d(vec3 axis, float angle) {
    axis = normalize(axis);
    float s = sin(angle);
    float c = cos(angle);
    float oc = 1.0 - c;

    return mat4(
      oc * axis.x * axis.x + c,           oc * axis.x * axis.y - axis.z * s,  oc * axis.z * axis.x + axis.y * s,  0.0,
      oc * axis.x * axis.y + axis.z * s,  oc * axis.y * axis.y + c,           oc * axis.y * axis.z - axis.x * s,  0.0,
      oc * axis.z * axis.x - axis.y * s,  oc * axis.y * axis.z + axis.x * s,  oc * axis.z * axis.z + c,           0.0,
      0.0,                                0.0,                                0.0,                                1.0
    );
  }

  void main() {
    vUv = uv;
    vec3 pos = position;

    #ifdef SHAPE_BOX
      float angle = pos.x * 0.1 * uDistort;
      pos = (rotation3d(vec3(1., 0., 0.), angle) * vec4(pos, 1.)).xyz;
    #endif

    vPosition = pos;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.);
  }
`

const FRAGMENT = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vPosition;

  uniform float uTime;
  uniform vec2 uRepeat;
  uniform vec3 uFog;
  uniform sampler2D uTexture;

  void main() {
    vec3 fragColor;

    #ifdef SHAPE_TORUS
      float time = uTime * 0.42;
      vec2 uv = fract(vUv * -uRepeat - vec2(time, 0.));
      vec3 tex = texture2D(uTexture, uv).rgb;
      // Depth gradient for rich 3D immersion
      float fog = clamp((vPosition.z + 10.0) / 18.0, 0.0, 1.0);
      fragColor = mix(uFog, tex, fog);
    #endif

    #ifdef SHAPE_BOX
      float time = uTime * 0.28;
      vec2 uv = fract(vUv * uRepeat - vec2(time, 0.));
      fragColor = texture2D(uTexture, uv).rgb;
    #endif

    gl_FragColor = vec4(fragColor, 1.0);
  }
`

function buildGeometry(shape) {
  if (shape === 'box') return new THREE.BoxGeometry(100, 10, 10, 64, 64, 64)
  return new THREE.TorusKnotGeometry(9, 3, 768, 4, 4, 3)
}

function definesFor(shape) {
  return shape === 'box' ? { SHAPE_BOX: true } : { SHAPE_TORUS: true }
}

class KineticScene {
  constructor(container, cfg) {
    this.container = container
    this.cfg = cfg
    const S = settingsFor(cfg)

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    const canvas = this.renderer.domElement
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;'
    container.appendChild(canvas)

    this.scene = new THREE.Scene()
    this.camera = new THREE.PerspectiveCamera(45, 1, 1, 1000)

    this.width = 1
    this.height = 1
    this.time = 0
    this.lastT = 0
    this.frameId = 0
    this.disposed = false
    this.grip = 0
    this.hovered = false
    this.pointer = { x: 0, y: 0, targetX: 0, targetY: 0 }

    this.onEnter = () => { this.hovered = true }
    this.onLeave = () => {
      this.hovered = false
      this.pointer.targetX = 0
      this.pointer.targetY = 0
    }
    this.onMove = (e) => {
      const rect = canvas.getBoundingClientRect()
      this.pointer.targetX = ((e.clientX - rect.left) / rect.width) * 2 - 1
      this.pointer.targetY = ((e.clientY - rect.top) / rect.height) * 2 - 1
    }

    canvas.addEventListener('pointerenter', this.onEnter)
    canvas.addEventListener('pointerleave', this.onLeave)
    canvas.addEventListener('pointercancel', this.onLeave)
    canvas.addEventListener('pointermove', this.onMove, { passive: true })

    // Offscreen plate canvas for type rendering
    this.plate = document.createElement('canvas')
    this.plate.width = TILE_W
    this.plate.height = TILE_H
    this.plateCtx = this.plate.getContext('2d')

    this.texture = new THREE.CanvasTexture(this.plate)
    this.texture.colorSpace = THREE.SRGBColorSpace
    this.texture.wrapS = THREE.RepeatWrapping
    this.texture.wrapT = THREE.RepeatWrapping
    this.texture.anisotropy = Math.min(this.renderer.capabilities.getMaxAnisotropy(), 16)
    this.drawPlate()

    this.geometry = buildGeometry(S.shape)
    this.material = new THREE.ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      defines: definesFor(S.shape),
      uniforms: {
        uTime: { value: 0 },
        uRepeat: { value: new THREE.Vector2(S.repeat[0], S.repeat[1]) },
        uDistort: { value: S.distort },
        uFog: { value: new THREE.Color(cfg.fogColor || cfg.fill || DEFAULTS.fill) },
        uTexture: { value: this.texture },
      },
      side: THREE.DoubleSide,
    })

    this.mesh = new THREE.Mesh(this.geometry, this.material)
    this.scene.add(this.mesh)

    const fonts = document.fonts
    if (fonts?.ready?.then) {
      fonts.ready.then(() => {
        if (!this.disposed) this.drawPlate()
      })
    }
  }

  drawPlate() {
    const ctx = this.plateCtx
    if (!ctx) return
    const S = settingsFor(this.cfg)
    const word = (this.cfg.word ?? '').length ? this.cfg.word : DEFAULTS.word

    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.fillStyle = this.cfg.fill || DEFAULTS.fill
    ctx.fillRect(0, 0, TILE_W, TILE_H)

    const BASIS = 200
    ctx.font = `${S.fontStyle} ${S.weight} ${BASIS}px ${S.family}`
    if ('letterSpacing' in ctx) ctx.letterSpacing = `${S.tracking}px`
    const m = ctx.measureText(word)
    const w = Math.max(1, m.width)
    const ascent = m.actualBoundingBoxAscent || BASIS * 0.72
    const descent = m.actualBoundingBoxDescent || 0
    const h = Math.max(1, ascent + descent)

    ctx.translate(TILE_W / 2, TILE_H / 2)
    ctx.scale((FILL_W * TILE_W) / w, S.capHeight / h)
    ctx.fillStyle = this.cfg.color || DEFAULTS.color
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(word, 0, h / 2 - descent)
    ctx.setTransform(1, 0, 0, 1, 0, 0)

    this.texture.needsUpdate = true
  }

  start() {
    this.lastT = performance.now()
    const loop = () => {
      if (this.disposed) return
      this.frameId = requestAnimationFrame(loop)
      this.step()
    }
    this.frameId = requestAnimationFrame(loop)
  }

  setSize(width, height) {
    if (this.disposed) return
    this.width = Math.max(1, width)
    this.height = Math.max(1, height)
    this.renderer.setSize(this.width, this.height, false)
    this.updateCamera()
  }

  updateCamera() {
    const aspect = this.width / this.height
    const S = settingsFor(this.cfg)
    const span = SPAN * S.zoom
    const visibleHeight = aspect < 1 ? span / aspect : span

    this.camera.aspect = aspect
    this.camera.position.set(0, 0, CAM_DISTANCE)
    this.camera.lookAt(0, 0, 0)
    this.camera.fov = 2 * Math.atan(visibleHeight / 2 / CAM_DISTANCE) * (180 / Math.PI)
    this.camera.near = Math.max(0.1, CAM_DISTANCE - 40)
    this.camera.far = CAM_DISTANCE + 40
    this.camera.updateProjectionMatrix()
  }

  step() {
    const now = performance.now()
    let dt = (now - this.lastT) / 1000
    this.lastT = now
    if (!isFinite(dt) || dt < 0) dt = 0
    if (dt > 0.05) dt = 0.05

    const S = settingsFor(this.cfg)
    const target = this.hovered && S.hoverBoost > 0 ? 1 : 0
    this.grip += (target - this.grip) * (1 - Math.exp(-dt * 4))
    this.time += dt * S.speed * (1 + this.grip * S.hoverBoost)
    this.material.uniforms.uTime.value = this.time

    // Interactive mouse rotation damping
    this.pointer.x += (this.pointer.targetX - this.pointer.x) * 0.08
    this.pointer.y += (this.pointer.targetY - this.pointer.y) * 0.08

    this.mesh.rotation.y = this.time * 0.05 + this.pointer.x * 0.4
    this.mesh.rotation.x = Math.sin(this.time * 0.03) * 0.15 - this.pointer.y * 0.35

    this.renderer.render(this.scene, this.camera)
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.frameId)
    this.geometry.dispose()
    this.material.dispose()
    this.texture.dispose()
    this.renderer.dispose()
    const canvas = this.renderer.domElement
    canvas.removeEventListener('pointerenter', this.onEnter)
    canvas.removeEventListener('pointerleave', this.onLeave)
    canvas.removeEventListener('pointercancel', this.onLeave)
    canvas.removeEventListener('pointermove', this.onMove)
    if (canvas.parentNode === this.container) this.container.removeChild(canvas)
  }
}

export default function KineticType({
  shape = DEFAULTS.shape,
  word = DEFAULTS.word,
  color = DEFAULTS.color,
  fill = DEFAULTS.fill,
  fogColor = DEFAULTS.fogColor,
  density = DEFAULTS.density,
  speed = DEFAULTS.speed,
  distort = DEFAULTS.distort,
  sizePercent = DEFAULTS.sizePercent,
  hoverBoost = DEFAULTS.hoverBoost,
  font = DEFAULTS.font,
  style,
}) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)

  const cfg = {
    shape,
    word,
    font,
    color,
    fill,
    fogColor,
    density,
    speed,
    distort,
    sizePercent,
    hoverBoost,
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let scene
    try {
      scene = new KineticScene(container, cfg)
    } catch (e) {
      console.warn('KineticType WebGL init failed:', e)
      return
    }
    sceneRef.current = scene
    scene.setSize(container.clientWidth, container.clientHeight)
    scene.start()

    const ro = new ResizeObserver(() => {
      if (container) scene.setSize(container.clientWidth, container.clientHeight)
    })
    ro.observe(container)

    return () => {
      ro.disconnect()
      scene.dispose()
      sceneRef.current = null
    }
  }, [])

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={`Kinetic typography: ${word}`}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minWidth: 120,
        minHeight: 120,
        overflow: 'hidden',
        ...style,
      }}
    />
  )
}
