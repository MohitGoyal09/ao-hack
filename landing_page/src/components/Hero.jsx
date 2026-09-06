import { motion } from 'framer-motion'
import RuxScene from '../three/RuxCore'

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.15 } },
}

const item = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.2, 0.8, 0.2, 1] } },
}

const stats = [
  { num: '46', label: 'backend tests passing' },
  { num: '100%', label: 'fail-closed evidence' },
  { num: '0', label: 'secrets pushed' },
  { num: '1', label: 'deterministic engine' },
]

export default function Hero() {
  return (
    <section className="hero" id="top">
      <div className="hero-inner">
        <motion.div className="hero-copy" variants={container} initial="hidden" animate="show">
          <motion.div variants={item}>
            <span className="badge">
              <span className="badge-dot" />
              Agentic covenant engine · v0.6
            </span>
          </motion.div>

          <motion.h1 className="hero-title" variants={item}>
            Read the covenant.
            <br />
            <span className="em">Bind</span> the truth.
          </motion.h1>

          <motion.p className="hero-sub" variants={item}>
            Rux ingests financial agreements, computes covenant ratios with
            deterministic arithmetic, fails ambiguous evidence{' '}
            <strong>closed</strong> to human review, and binds every officer
            approval to the exact revision it governs.
          </motion.p>

          <motion.div className="hero-cta" variants={item} id="hero-cta">
            <a className="btn btn-primary" href="#engine">
              Explore the engine
            </a>
            <a className="btn btn-ghost" href="#status">
              See where Rux stands <span className="mono">v0.6</span>
            </a>
          </motion.div>

          <motion.div className="hero-stats" variants={item}>
            {stats.map((s) => (
              <div className="stat" key={s.label}>
                <span className="stat-num">{s.num}</span>
                <span className="stat-label">{s.label}</span>
              </div>
            ))}
          </motion.div>
        </motion.div>

        <motion.div
          className="hero-visual"
          initial={{ opacity: 0, scale: 0.94, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 1.1, ease: [0.2, 0.8, 0.2, 1], delay: 0.25 }}
        >
          <RuxScene />
        </motion.div>
      </div>

      <div className="scroll-hint" aria-hidden="true">
        <span className="scroll-hint-line" />
      </div>
    </section>
  )
}