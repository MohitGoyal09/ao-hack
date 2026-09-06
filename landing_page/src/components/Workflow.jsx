import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const steps = [
  {
    id: '01',
    name: 'Ingest & Normalisation',
    badge: 'STAGE 01',
    tagline: 'Multi-modal PDF parsing & schema hydration',
    body: 'Raw loan agreements, credit facilities, and compliance certificates are parsed with coordinate-aware OCR, normalized into strict JSON schemas, and persisted in Supabase.',
    tags: ['pdfplumber + OCR', 'Supabase Schema', 'BBox Anchors', 'JSON Schema v2'],
    sla: '< 120ms',
    input: 'Unstructured PDF (Credit Agreement, 48 pages)',
    output: 'Canonical Case Document (AST Schema v2.4)',
    status: 'PARSED & HYDRATED',
    statusClass: 'status-ready',
    codeLanguage: 'json',
    codeSnippet: `{
  "stage": "01_INGEST",
  "document_id": "doc_8f92a10b",
  "source": "TermLoan_CreditAgreement_2025.pdf",
  "pages_processed": 48,
  "tables_extracted": 14,
  "bounding_boxes": [
    {
      "clause": "§7.1(a) Total Net Leverage",
      "page": 32,
      "bbox": [142, 310, 520, 398],
      "confidence": 0.9984
    }
  ],
  "schema_status": "VALIDATED_CANONICAL"
}`,
  },
  {
    id: '02',
    name: 'Deterministic Computation',
    badge: 'STAGE 02',
    tagline: 'Safe-Python AST arithmetic with zero float drift',
    body: 'Financial ratios are calculated inside a sandboxed, pure-Python AST evaluator. Arithmetic uses fixed-precision decimals rather than IEEE 754 floating point to prevent silent cross-platform drift.',
    tags: ['Safe-Python AST', 'Fixed-Point Decimals', 'Zero Float Drift', 'Line-by-Line Formula'],
    sla: '< 35ms',
    input: 'Debt: $98.0M | EBITDA: $45.2M | Threshold: 2.50x',
    output: 'Leverage: 2.1681x (<= 2.5000x) -> PASS',
    status: 'COMPUTED (ZERO DRIFT)',
    statusClass: 'status-pass',
    codeLanguage: 'python',
    codeSnippet: `# Pure-Python AST Evaluator (Fixed Precision)
debt = Decimal("98000000.00")
ebitda = Decimal("45200000.00")
threshold = Decimal("2.5000")

# Executing deterministic ratio computation:
ratio = debt / ebitda  # Decimal('2.1681415929')
is_compliant = ratio <= threshold  # True

return ComputationResult(
    covenant="Total Net Leverage",
    computed_value=ratio.quantize(Decimal('0.0001')),
    threshold=threshold,
    comparator="<=",
    verdict="COMPLIANT"
)`,
  },
  {
    id: '03',
    name: 'Fail-Closed Verification',
    badge: 'STAGE 03',
    tagline: 'Zero tolerance for ambiguous or stale evidence',
    body: 'If any required clause citation, coordinate anchor, or formula input contains ambiguity, or if a revision is stale, the engine halts execution immediately and routes the case to the officer review queue.',
    tags: ['Fail-Closed Gate', 'Confidence Scoring', 'Human Review Queue', 'Citation Anchoring'],
    sla: 'Instant Gate',
    input: 'Confidence: 0.9984 | Citation: Verified | Stale Check: False',
    output: 'Gate Clear -> Proceed to Seal (0 False Positives)',
    status: 'GATE CLEARED (FAIL-CLOSED)',
    statusClass: 'status-pass',
    codeLanguage: 'json',
    codeSnippet: `{
  "stage": "03_VERIFY",
  "policy": "FAIL_CLOSED_ON_AMBIGUITY",
  "verification_checks": {
    "citation_bounds_checked": true,
    "input_freshness_verified": true,
    "ambiguity_score": 0.000,
    "stale_revision_detected": false
  },
  "gate_decision": "ALLOW_APPROVAL",
  "escalation_path": "NONE (Human queue idle)",
  "audit_checkpoint": "chk_verify_998a1"
}`,
  },
  {
    id: '04',
    name: 'Cryptographic Revision Seal',
    badge: 'STAGE 04',
    tagline: 'Officer digital signature bound to package hash',
    body: 'When an authorized officer signs off, an Ed25519 signature permanently seals the revision hash, inputs, formula AST, threshold, comparator, and timestamp into an immutable ledger lock.',
    tags: ['Ed25519 Signature', 'SHA-256 Package Hash', 'Officer Lock', 'Non-Repudiation'],
    sla: '< 15ms',
    input: 'Officer ID: usr_cfo_09 | Revision: rev_89f02c',
    output: 'Seal: 0x7a8e...4f1d (SHA-256 Bound)',
    status: 'SEALED & LOCKED',
    statusClass: 'status-seal',
    codeLanguage: 'json',
    codeSnippet: `{
  "stage": "04_APPROVE",
  "package_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
  "officer_signature": {
    "officer_id": "usr_cfo_09_mgo",
    "algorithm": "Ed25519",
    "signature": "0x7a8e41bf98204ca810f92d4710ebac538190fa72810f912c4f1d",
    "timestamp": "2025-09-06T14:40:00.000Z",
    "sealed_attributes": [
      "ratio", "threshold", "comparator", "inputs", "evidence_hash"
    ]
  }
}`,
  },
  {
    id: '05',
    name: 'Postgres WAL Replay & Audit',
    badge: 'STAGE 05',
    tagline: 'Durable state checkpointer with 100% replay guarantee',
    body: 'Every event transition is committed to Postgres Write-Ahead Logs via LangGraph checkpointer. The trail replays deterministically: /health/ready proves database durability without silent in-memory fallback.',
    tags: ['Postgres WAL', 'LangGraph Checkpointer', 'Durable Replay', '/health/ready Proof'],
    sla: '100% Replayable',
    input: 'Audit Query: Replay Case #89102 from Genesis',
    output: 'Bit-for-bit matched state (Replay Verified)',
    status: 'DURABLE & REPLAYABLE',
    statusClass: 'status-ready',
    codeLanguage: 'json',
    codeSnippet: `{
  "stage": "05_REPLAY",
  "database": "PostgreSQL 16 (WAL Enabled)",
  "health_check": {
    "endpoint": "/health/ready",
    "status": "HEALTHY",
    "in_memory_fallback": false,
    "uncheckpointed_events": 0
  },
  "replay_verification": {
    "total_events_replayed": 184,
    "divergence_count": 0,
    "audit_proof": "DURABLE_MATCH_CONFIRMED"
  }
}`,
  },
]

export default function Workflow() {
  const [activeIdx, setActiveIdx] = useState(0)
  const current = steps[activeIdx]

  return (
    <section className="section" id="workflow">
      <div className="section-head">
        <span className="eyebrow">Execution Pipeline</span>
        <h2 className="section-title">
          From raw PDF to a decision <span className="em">under lock.</span>
        </h2>
        <p className="section-sub">
          One unified pipeline, five deterministic guarantees. Every transition is checkpointed
          and every outcome is mathematically locked to a revision.
        </p>
      </div>

      {/* Workflow Stats Overview Bar */}
      <div className="workflow-metrics-bar">
        <div className="wf-metric-item">
          <span className="wf-metric-num">5</span>
          <span className="wf-metric-label">Checkpointed Stages</span>
        </div>
        <div className="wf-metric-divider" />
        <div className="wf-metric-item">
          <span className="wf-metric-num">0</span>
          <span className="wf-metric-label">Silent Fallbacks</span>
        </div>
        <div className="wf-metric-divider" />
        <div className="wf-metric-item">
          <span className="wf-metric-num">&lt; 150ms</span>
          <span className="wf-metric-label">End-to-End Latency</span>
        </div>
        <div className="wf-metric-divider" />
        <div className="wf-metric-item">
          <span className="wf-metric-num">Ed25519</span>
          <span className="wf-metric-label">Revision Seal</span>
        </div>
      </div>

      {/* Main 2-Column Command Center */}
      <div className="workflow-grid">
        {/* Left Column: Interactive Stage Cards */}
        <div className="workflow-stages-col">
          <div className="workflow-track-line" />
          {steps.map((s, idx) => {
            const isActive = idx === activeIdx
            return (
              <motion.article
                key={s.id}
                className={`wf-stage-card ${isActive ? 'is-active' : ''}`}
                onClick={() => setActiveIdx(idx)}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.5, delay: idx * 0.08 }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setActiveIdx(idx)
                  }
                }}
              >
                <div className="wf-card-header">
                  <div className="wf-stage-badge-group">
                    <span className="wf-stage-pill">{s.id}</span>
                    <span className="wf-stage-subpill">{s.badge}</span>
                  </div>
                  <span className="wf-sla-tag mono">{s.sla}</span>
                </div>

                <h3 className="wf-stage-title">{s.name}</h3>
                <p className="wf-stage-tagline">{s.tagline}</p>
                <p className="wf-stage-desc">{s.body}</p>

                {/* Tech Tags */}
                <div className="wf-tags-list">
                  {s.tags.map((tag) => (
                    <span key={tag} className="wf-tag-pill mono">
                      {tag}
                    </span>
                  ))}
                </div>

                {/* Data Flow I/O Strip */}
                <div className="wf-io-strip">
                  <div className="wf-io-row">
                    <span className="wf-io-lbl mono">IN</span>
                    <span className="wf-io-val mono">{s.input}</span>
                  </div>
                  <div className="wf-io-row">
                    <span className="wf-io-lbl mono">OUT</span>
                    <span className="wf-io-val mono wf-io-val-out">{s.output}</span>
                  </div>
                </div>

                {/* Active indicator bar */}
                <div className="wf-card-status-bar">
                  <span className="wf-status-bullet" />
                  <span className="wf-status-text mono">
                    {isActive ? 'Active Telemetry Stream' : 'Click to inspect stage payload'}
                  </span>
                  <span className="wf-arrow-hint mono">{isActive ? '● LIVE' : '→'}</span>
                </div>
              </motion.article>
            )
          })}
        </div>

        {/* Right Column: Live Pipeline State Telemetry Inspector */}
        <div className="workflow-inspector-col">
          <div className="wf-inspector-card">
            {/* Inspector Top Bar */}
            <div className="wf-insp-topbar">
              <div className="wf-insp-dots">
                <span className="dot dot-red" />
                <span className="dot dot-amber" />
                <span className="dot dot-green" />
              </div>
              <div className="wf-insp-title mono">
                <span>STAGE_{current.id}</span> // <span>{current.name.toUpperCase()}</span>
              </div>
              <div className="wf-insp-badge mono">
                <span className="wf-insp-live-dot" />
                <span>{current.status}</span>
              </div>
            </div>

            {/* Inspector Sub Bar */}
            <div className="wf-insp-meta-strip mono">
              <div className="wf-meta-cell">
                <span className="wf-meta-k">STAGE SLA</span>
                <span className="wf-meta-v">{current.sla}</span>
              </div>
              <div className="wf-meta-cell">
                <span className="wf-meta-k">RUNTIME</span>
                <span className="wf-meta-v">AST Sandbox</span>
              </div>
              <div className="wf-meta-cell">
                <span className="wf-meta-k">LEDGER</span>
                <span className="wf-meta-v">WAL Sealed</span>
              </div>
            </div>

            {/* Code / Payload Viewer */}
            <div className="wf-insp-code-body">
              <div className="wf-code-header mono">
                <span>PAYLOAD_INSPECTOR.json</span>
                <span className="wf-code-lang">{current.codeLanguage}</span>
              </div>
              <AnimatePresence mode="wait">
                <motion.pre
                  key={current.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  className="wf-code-block mono"
                >
                  <code>{current.codeSnippet}</code>
                </motion.pre>
              </AnimatePresence>
            </div>

            {/* I/O Payload Inspection Box */}
            <div className="wf-insp-io-box">
              <div className="wf-insp-io-item">
                <span className="wf-insp-io-title mono">INPUT STREAM</span>
                <span className="wf-insp-io-content mono">{current.input}</span>
              </div>
              <div className="wf-insp-io-item wf-insp-io-item-out">
                <span className="wf-insp-io-title mono">SEALED ARTIFACT</span>
                <span className="wf-insp-io-content mono">{current.output}</span>
              </div>
            </div>

            {/* Stage Quick Switcher Footer */}
            <div className="wf-insp-footer">
              <button
                type="button"
                className="wf-nav-btn mono"
                disabled={activeIdx === 0}
                onClick={() => setActiveIdx((prev) => Math.max(0, prev - 1))}
              >
                &larr; Prev Stage
              </button>

              <div className="wf-stage-dots-nav">
                {steps.map((st, i) => (
                  <button
                    key={st.id}
                    type="button"
                    className={`wf-dot-btn ${i === activeIdx ? 'is-active' : ''}`}
                    onClick={() => setActiveIdx(i)}
                    title={`Stage ${st.id}: ${st.name}`}
                  >
                    <span className="mono">{st.id}</span>
                  </button>
                ))}
              </div>

              <button
                type="button"
                className="wf-nav-btn mono"
                disabled={activeIdx === steps.length - 1}
                onClick={() => setActiveIdx((prev) => Math.min(steps.length - 1, prev + 1))}
              >
                Next Stage &rarr;
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}