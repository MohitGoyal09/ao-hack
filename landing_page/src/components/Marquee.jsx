const items = [
  'LangGraph',
  'FastAPI',
  'Supabase',
  'Postgres',
  'CopilotKit',
  'AG-UI',
  'Next.js',
  'Gemini',
  'Deterministic Math',
  'Durable Queues',
  'RLS Security',
  'Human Review',
]

export default function Marquee() {
  const row = [...items, ...items]
  return (
    <div className="marquee">
      <div className="marquee-track">
        {row.map((t, i) => (
          <span className="marquee-item" key={`${t}-${i}`}>
            {t}
            <i className="marquee-star" aria-hidden="true">
              ✦
            </i>
          </span>
        ))}
      </div>
    </div>
  )
}