import { motion } from 'framer-motion'

const cards = [
  {
    tag: 'Math',
    title: 'Deterministic covenant math',
    body: 'Safe-Python arithmetic locks every ratio, threshold and comparator to the same exact result on every runtime. No float drift, no probabilistic inference, no silent drift between environments.',
    chip: 'ratio 2.40x · threshold 1.75x → passed',
  },
  {
    tag: 'Evidence',
    title: 'Evidence that fails closed',
    body: 'When a number is missing or unclear, Rux never guesses. The signal routes straight to human review — ambiguity becomes visibility, not risk.',
    chip: 'status: review → assigned to human',
  },
  {
    tag: 'Approval',
    title: 'Revisions & bound approvals',
    body: 'Amendments and threshold changes become revisable revisions. An officer approval binds to the revision, package hash, ratio and inputs — exact, immutable, auditable.',
    chip: 'approval → bound to hash: c3f7…a9',
  },
]

export default function Engine() {
  return (
    <section className="section" id="engine">
      <div className="section-head">
        <span className="eyebrow">The engine</span>
        <h2 className="section-title">
          Three guarantees. <span className="em">One</span> engine.
        </h2>
        <p className="section-sub">
          Rux is built around properties that must never bend: determinism,
          fail-closed evidence, and approvals that survive auditing.
        </p>
      </div>

      <div className="card-grid">
        {cards.map((c, i) => (
          <motion.article
            className="card"
            key={c.title}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, ease: [0.2, 0.8, 0.2, 1], delay: i * 0.12 }}
          >
            <span className="card-tag">{c.tag}</span>
            <h3 className="card-title">{c.title}</h3>
            <p className="card-body">{c.body}</p>
            <span className="card-chip mono">{c.chip}</span>
          </motion.article>
        ))}
      </div>
    </section>
  )
}