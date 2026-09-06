import * as THREE from 'three'

export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

export function glowTexture(inner, outer) {
  const c = document.createElement('canvas')
  c.width = 128
  c.height = 128
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 2, 64, 64, 64)
  g.addColorStop(0, inner)
  g.addColorStop(1, outer)
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}

export function makeLabelTexture(text) {
  const c = document.createElement('canvas')
  c.width = 640
  c.height = 200
  const ctx = c.getContext('2d')

  roundRect(ctx, 10, 10, 620, 180, 44)
  ctx.fillStyle = 'rgba(253, 252, 246, 0.96)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(36, 34, 24, 0.32)'
  ctx.lineWidth = 4
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(58, 100, 22, 0, Math.PI * 2)
  ctx.fillStyle = '#146f69'
  ctx.fill()

  ctx.font = '500 62px "JetBrains Mono", monospace'
  ctx.fillStyle = '#146f69'
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'left'
  ctx.fillText(text, 108, 106)

  const t = new THREE.CanvasTexture(c)
  t.anisotropy = 8
  t.colorSpace = THREE.SRGBColorSpace
  return t
}