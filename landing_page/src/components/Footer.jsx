import Logo from './Logo'

export default function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-top">
          <div className="footer-brand-wrap">
            <a className="brand" href="#top" aria-label="Rux home">
              <Logo size={110} />
              <span className="brand-word">RUX</span>
            </a>
            <p className="footer-tag">
              The Autonomous Covenant Engine. Deterministic math, fail-closed
              evidence, and human-owned decisions.
            </p>
          </div>

          <div className="footer-nav-grid">
            <div>
              <h4 className="footer-col-title">Product</h4>
              <nav className="footer-links" aria-label="Product Links">
                <a href="#engine">Deterministic Engine</a>
                <a href="#workflow">5-Stage Pipeline</a>
                <a href="#review">Human-in-the-Loop</a>
                <a href="#status">Release Status</a>
              </nav>
            </div>

            <div>
              <h4 className="footer-col-title">Architecture</h4>
              <nav className="footer-links" aria-label="Architecture Links">
                <a href="#top">LangGraph Core</a>
                <a href="#top">FastAPI + Supabase</a>
                <a href="#top">Safe-Python Sandbox</a>
                <a href="#top">Audit Replay</a>
              </nav>
            </div>

            <div>
              <h4 className="footer-col-title">Navigation</h4>
              <nav className="footer-links" aria-label="Page Navigation">
                <a href="#top">Back to top ↑</a>
                <a href="#hero-cta">Get Started</a>
                <a href="#review">Review Policies</a>
              </nav>
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <div className="footer-copy">
            <span>© {currentYear} Rux Inc. All rights reserved.</span>
          </div>
          <div className="footer-badge">
            <span>● 46 Tests Passing</span>
            <span>·</span>
            <span>Deterministic v0.6</span>
          </div>
        </div>
      </div>
    </footer>
  )
}