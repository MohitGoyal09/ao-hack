import { motion } from 'framer-motion'

const steps = [
  {
    id: '01',
    name: 'Ingest',
    body: 'Aon PDFs and financial data are extracted, normalised, and stored into a case under the Supabase schema.',
    out: 'extract() → document v1',
  },
  {
    id: '02',
    name: 'Compute',
    body: 'Covenant ratios are computed with deterministic safe-Python arithmetic and compared line-by-line to thresholds.',
    out: 'calc() → 2.40x',
  },
  {
    id: '03',
    name: 'Review',
    body: 'Missing or unclear evidence — and any stale decision — fails closed into a human review queue.',
    out: 'assert() → human',
  },
  {
    id: '04',
    name: 'Approve',
    body: 'An exact officer approval binds the decision to the revision, package hash, ratio, threshold, comparator, and inputs.',
    out: 'sign(hash)',
  },
  {
    id: '05',
    name: 'Replay',
    body: 'Every event is checkpointed. The trail replays durably — /health/ready tells the truth about the database. No silent memory fallback.',
    out: 'replay() → audit',
  },
]

export default function Workflow() {
  return (
    <section className="section" id="workflow">
      <div className="section-head">
        <span className="eyebrow">Workflow</span>
        <h2 className="section-title">
          From raw PDF to a decision <span className="em">under lock.</span>
        </h2>
        <p className="section-sub">
          One pipeline, five guarantees. Every transition is checkpointed and
          every outcome is attributable to a specific revision.
        </p>
      </div>

      <motion.div
        className="workflow-panel"
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <div className="timeline">
          {steps.map((s) => (
            <article className="step" key={s.id}>
              <span className="step-dot" aria-hidden="true" />
              <div>
                <span className="step-id">{s.id}</span>
                <h3 className="step-name">{s.name}</h3>
                <p className="step-body">{s.body}</p>
              </div>
              <span className="step-out mono">{s.out}</span>
            </article>
          ))}
        </div>
      </motion.div>
    </section>
  )
}