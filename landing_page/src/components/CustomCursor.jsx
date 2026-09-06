import { useEffect, useState } from 'react'

export default function CustomCursor() {
  const [pos, setPos] = useState({ x: -100, y: -100 })
  const [hovered, setHovered] = useState(false)
  const [clicked, setClicked] = useState(false)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.matchMedia('(hover: none)').matches) return

    let mouseX = -100
    let mouseY = -100
    let curX = -100
    let curY = -100
    let rafId

    const onMouseMove = (e) => {
      mouseX = e.clientX
      mouseY = e.clientY
      if (!visible) setVisible(true)

      const target = e.target
      const isClickable = Boolean(
        target &&
          target.closest &&
          target.closest('a, button, .btn, .card, canvas, [role="button"], input, .stat')
      )
      setHovered(isClickable)
    }

    const onMouseDown = () => setClicked(true)
    const onMouseUp = () => setClicked(false)
    const onMouseLeave = () => setVisible(false)
    const onMouseEnter = () => setVisible(true)

    const loop = () => {
      curX += (mouseX - curX) * 0.22
      curY += (mouseY - curY) * 0.22
      setPos({ x: curX, y: curY })
      rafId = requestAnimationFrame(loop)
    }

    window.addEventListener('mousemove', onMouseMove, { passive: true })
    window.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mouseup', onMouseUp)
    document.addEventListener('mouseleave', onMouseLeave)
    document.addEventListener('mouseenter', onMouseEnter)
    rafId = requestAnimationFrame(loop)

    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mouseup', onMouseUp)
      document.removeEventListener('mouseleave', onMouseLeave)
      document.removeEventListener('mouseenter', onMouseEnter)
      cancelAnimationFrame(rafId)
    }
  }, [visible])

  if (!visible) return null

  return (
    <div
      className={`custom-cursor ${hovered ? 'is-hover' : ''} ${clicked ? 'is-clicked' : ''}`}
      style={{
        transform: `translate3d(${pos.x}px, ${pos.y}px, 0)`,
      }}
      aria-hidden="true"
    >
      <div className="cursor-ring" />
      <div className="cursor-logo">
        <svg viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M18 36 C16 48 24 64 42 74 C58 82 72 82 82 78 C64 80 46 72 34 60 C24 50 20 42 18 36 Z"
            fill="currentColor"
          />
          <path
            d="M122 64 C124 52 116 36 98 26 C82 18 68 18 58 22 C76 20 94 28 106 40 C116 50 120 58 122 64 Z"
            fill="currentColor"
          />
          <path
            d="M38 46 C38 30 52 18 70 18 C86 18 98 24 104 30 C94 32 80 37 68 43 C54 50 44 60 40 70 C36 58 36 48 38 46 Z"
            fill="currentColor"
          />
          <path
            d="M102 54 C102 70 88 82 70 82 C54 82 42 76 36 70 C46 68 60 63 72 57 C86 50 96 40 100 30 C104 42 104 52 102 54 Z"
            fill="currentColor"
          />
          <path
            d="M98 32 C84 38 72 43 56 46"
            stroke="#f7f5ec"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
          <path
            d="M42 68 C56 62 68 57 84 54"
            stroke="#f7f5ec"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
          <circle cx="56" cy="46" r="7.5" fill="#f7f5ec" />
          <circle cx="56" cy="46" r="4.2" fill="currentColor" />
          <circle cx="84" cy="54" r="7.5" fill="#f7f5ec" />
          <circle cx="84" cy="54" r="4.2" fill="currentColor" />
        </svg>
      </div>
      <div className="cursor-dot" />
    </div>
  )
}
