import { motion } from 'framer-motion'

const links = [
  { href: '#engine', label: 'Engine' },
  { href: '#workflow', label: 'Workflow' },
  { href: '#review', label: 'Review' },
  { href: '#status', label: 'Status' },
]

export default function Nav() {
  return (
    <header className="nav">
      <div className="nav-inner">
        <a className="brand" href="#top" aria-label="Rux — home">
          <LogoMark />
          <span className="brand-word">RUX</span>
        </a>
        <nav className="nav-links" aria-label="Primary">
          {links.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <a className="btn btn-primary btn-sm" href="#hero-cta">
          Get started
        </a>
      </div>
    </header>
  )
}

function LogoMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="38" height="38" rx="10" fill="#146f69" />
      <circle cx="20" cy="20" r="7" stroke="#f7f5ec" strokeWidth="1.6" />
      <circle cx="20" cy="20" r="2.8" fill="#fdfcf6" />
      <ellipse
        cx="20"
        cy="20"
        rx="12.5"
        ry="4.5"
        stroke="#8ed3cc"
        strokeWidth="1.6"
        transform="rotate(-22 20 20)"
      />
      <circle cx="30.5" cy="13.5" r="1.6" fill="#8ed3cc" />
    </svg>
  )
}