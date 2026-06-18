const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

const RUBRIC = [
  { key: 'guardrail_adherence', label: 'Guardrail Adherence', weight: '20%' },
  { key: 'resolution_rate',     label: 'Resolution Rate',     weight: '30%' },
  { key: 'containment',         label: 'Containment',         weight: '15%' },
  { key: 'handle_time_score',   label: 'Handle Time',         weight: '5%'  },
  { key: 'disclosure_score',    label: 'Disclosure',          weight: '5%'  },
]

function scoreColor(score) {
  if (score >= 80) return Y
  if (score >= 60) return Wa(0.72)
  return Wa(0.38)
}

function ScoreBar({ score }) {
  const color = scoreColor(score)
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex-1 rounded-full overflow-hidden"
        style={{ height: 4, background: Wa(0.07) }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${score}%`,
            background: color,
            boxShadow: score >= 80 ? `0 0 6px ${Ya(0.4)}` : 'none',
          }}
        />
      </div>
      <span className="text-[12px] font-medium w-7 text-right" style={{ color }}>{score}</span>
    </div>
  )
}

export default function QAScorecard({ eval: ev }) {
  if (!ev) {
    return (
      <div className="rounded-2xl p-8 text-center"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
        <p className="t-body-14 text-white/45">Select a call to view QA scorecard</p>
      </div>
    )
  }

  const overall = ev.overall_score
  const isPassing = ev.pass_fail === 'PASS'
  const oColor = scoreColor(overall)
  const oGlow = overall >= 80 ? Ya(0.3) : 'transparent'

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: `1px solid ${Wa(0.06)}` }}
      >
        <div>
          <p className="text-[14px] font-medium text-white">
            {ev.customer_name || `Call ${ev.call_id?.slice(0, 8)}`}
          </p>
          <p className="t-caps text-white/42 mt-0.5 text-[10px]">
            {ev.call_started_at
              ? new Date(ev.call_started_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
              : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-[18px] font-light" style={{ color: oColor }}>
              {overall}/100
            </p>
            <span
              className="t-caps px-2 py-0.5 rounded-full text-[10px] inline-block"
              style={{
                color: isPassing ? Y : Wa(0.45),
                background: isPassing ? Ya(0.08) : Wa(0.04),
                border: `1px solid ${isPassing ? Ya(0.22) : Wa(0.10)}`,
              }}
            >
              {ev.pass_fail || '—'}
            </span>
          </div>
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{
              background: `${oColor}12`,
              border: `1.5px solid ${oColor}`,
              boxShadow: `0 0 12px ${oGlow}`,
            }}
          >
            <span className="text-[14px] font-semibold" style={{ color: oColor }}>{overall}</span>
          </div>
        </div>
      </div>

      {/* Rubric */}
      <div className="px-6 py-5 flex flex-col gap-3.5">
        <p className="section-label text-[10px]">Rubric Breakdown</p>
        {RUBRIC.map(({ key, label, weight }) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[12px] text-white/65">{label}</span>
              <span className="t-caps text-white/38 text-[10px]">{weight}</span>
            </div>
            <ScoreBar score={ev[key] ?? 0} />
          </div>
        ))}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[12px] text-white/65">Caller Satisfaction</span>
            <span className="t-caps text-white/38 text-[10px]">25%</span>
          </div>
          <ScoreBar score={Math.round((ev.caller_satisfaction ?? 0) * 100)} />
        </div>
      </div>

      {/* Coaching note */}
      {ev.coaching_note && (
        <div
          className="mx-6 mb-5 rounded-xl p-3.5"
          style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}
        >
          <p className="t-caps text-[10px] mb-1.5 flex items-center gap-1.5" style={{ color: Y }}>
            ✦ Coaching Note
          </p>
          <p className="text-[12px] text-white/65 leading-relaxed">{ev.coaching_note}</p>
        </div>
      )}

      {/* Customer feedback */}
      {ev.customer_rating != null && (
        <div
          className="mx-6 mb-5 rounded-xl p-3.5"
          style={{ background: Ya(0.03), border: `1px solid ${Ya(0.10)}` }}
        >
          <p className="t-caps text-[10px] mb-2" style={{ color: Ya(0.7) }}>Customer Feedback</p>
          <div className="flex items-center gap-1 mb-1">
            {[1, 2, 3, 4, 5].map(n => (
              <span key={n} style={{ fontSize: '15px', color: n <= ev.customer_rating ? Y : Wa(0.15) }}>★</span>
            ))}
            <span className="t-caps text-white/38 text-[10px] ml-1">{ev.customer_rating}/5</span>
          </div>
          {ev.customer_feedback && (
            <p className="text-[12px] text-white/60 mt-1 leading-relaxed">{ev.customer_feedback}</p>
          )}
        </div>
      )}
    </div>
  )
}
