import { motion } from 'framer-motion'

const guarantees = [
  {
    title: 'Fail-closed routing',
    body: 'Ambiguous or missing evidence always reaches a human reviewer — never a guess.',
  },
  {
    title: 'Exact officer approval',
    body: 'No delegated authority, no shadow sign-offs. The approval is precise and attributable.',
  },
  {
    title: 'Revision-bound decisions',
    body: 'An approval invalidates automatically the moment the agreement is amended.',
  },
  {
    title: 'Stale-decision rejection',
    body: 'The engine refuses to act on outdated computations. Stale means closed.',
  },
  {
    title: 'Readiness truth',
    body: '/health/live and /health/ready expose real database state — no silent in-memory fallback.',
  },
  {
    title: 'Durable queue',
    body: 'Leases, retries, heartbeats, cancellation, and stale-worker fencing keep work honest.',
  },
]

export default function HumanLoop() {
  return (
    <section className="section" id="review">
      <div className="human-grid">
        <div className="section-head" style={{ marginBottom: 0 }}>
          <span className="eyebrow">Human in the loop</span>
          <h2 className="section-title">
            Autonomy where safe. <br />
            Humans where it <span className="em">matters.</span>
          </h2>
          <p className="section-sub">
            Rux accelerates the trivial and escalates the consequential. The
            system decides only when the evidence is exact — everything else is
            routed, documented, and handed to a reviewer.
          </p>
          <pre className="human-code">
            <span className="c">// every unclear signal pauses here</span>
            {'\n'}
            <span className="k">const</span> verdict = <span className="k">await</span> rux.evaluate(case);
            {'\n'}
            <span className="k">if</span> (verdict.needsReview) <span className="k">→</span> officer.inbox
          </pre>
        </div>

        <ul className="guarantee-list">
          {guarantees.map((g, i) => (
            <motion.li
              className="guarantee"
              key={g.title}
              initial={{ opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1], delay: i * 0.07 }}
            >
              <span className="guarantee-check" aria-hidden="true">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M2.5 8.5l3.5 3.5 7.5-8"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <p>
                <strong>{g.title}.</strong> {g.body}
              </p>
            </motion.li>
          ))}
        </ul>
      </div>
    </section>
  )
}