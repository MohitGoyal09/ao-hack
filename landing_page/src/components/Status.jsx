import { motion } from 'framer-motion'

const shipped = [
  'Python FastAPI + LangGraph covenant backend',
  'Deterministic calculations · evidence checks · revisions',
  'Human review & exact officer approval flows',
  'Supabase schema, Auth/Storage adapters & Postgres job queue',
  'Next.js + CopilotKit + AG-UI frontend dashboard',
  'Fail-safe readiness with no silent in-memory fallback',
  '46 backend tests passing · frontend production build green',
]

const onDeck = [
  'Persistent Postgres revision repository',
  'Authenticated upload → revision workflow',
  'Production background worker wiring',
  'Durable LangGraph human pause / resume',
  'Durable AG-UI event replay',
  'Real Gemini / LiteLLM integration tests',
  'Full accuracy evaluation harness',
]

export default function Status() {
  return (
    <section className="section" id="status">
      <div className="section-head">
        <span className="eyebrow">Build status</span>
        <h2 className="section-title">
          Where Rux stands <span className="em">today.</span>
        </h2>
        <p className="section-sub">
          Core engine shipped and verified. The production workflow (live
          persistence, workers, and durable replay) is the next frontier.
        </p>
      </div>

      <div className="status-grid">
        <motion.div
          className="status-card"
          initial={{ opacity: 0, y: 26 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.6, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <span className="eyebrow">Shipped</span>
          <ul className="status-list">
            {shipped.map((t) => (
              <li key={t}>
                <svg
                  className="status-ok"
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M2.5 8.5l3.5 3.5 7.5-8"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {t}
              </li>
            ))}
          </ul>
        </motion.div>

        <motion.div
          className="status-card shade"
          initial={{ opacity: 0, y: 26 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.6, ease: [0.2, 0.8, 0.2, 1], delay: 0.12 }}
        >
          <span className="eyebrow">On deck</span>
          <ul className="status-list">
            {onDeck.map((t) => (
              <li key={t}>
                <span className="status-wait" aria-hidden="true">
                  ●
                </span>
                {t}
              </li>
            ))}
          </ul>
        </motion.div>
      </div>
    </section>
  )
}