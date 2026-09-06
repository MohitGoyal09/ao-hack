import Logo from './Logo'

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
        <a className="brand" href="#top" aria-label="Rux home">
          <Logo size={76} />
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