export default function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-top">
          <div>
            <span className="brand-word">RUX</span>
            <p className="footer-tag">
              The autonomous covenant engine. Deterministic math, fail-closed
              evidence, human-owned decisions.
            </p>
          </div>
          <nav className="footer-links" aria-label="Footer">
            <a href="#engine">Engine</a>
            <a href="#workflow">Workflow</a>
            <a href="#review">Review</a>
            <a href="#status">Status</a>
            <a href="#top">Back to top ↑</a>
          </nav>
        </div>
        <div className="footer-bottom">
          <span>© {year} Rux — cream, inked, exact.</span>
          <span>46 tests · 0 secrets · 1 engine</span>
        </div>
      </div>
    </footer>
  )
}