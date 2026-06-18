import { CheckCircle2, AlertCircle, ArrowRight, TrendingUp, TrendingDown, Minus } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function trendColor(t) {
  if (t === 'improving') return Y
  if (t === 'declining') return Wa(0.38)
  return Wa(0.52)
}

function TrendIcon({ trend }) {
  const color = trendColor(trend)
  if (trend === 'improving') return <TrendingUp  size={14} color={color} />
  if (trend === 'declining') return <TrendingDown size={14} color={color} />
  return <Minus size={14} color={color} />
}

function priorityStyle(p) {
  if (p === 'high')   return { color: Y,        bg: Ya(0.07), border: Ya(0.20) }
  if (p === 'medium') return { color: Wa(0.72), bg: Wa(0.04), border: Wa(0.12) }
  return                     { color: Wa(0.42), bg: Wa(0.02), border: Wa(0.08) }
}

export default function CoachingPackCard({ pack }) {
  if (!pack) return null

  const { overall_trend, strengths, improvements, action_items, score_summary, coaching_note, agent_name, generated_at } = pack
  const s = score_summary || {}
  const tc = trendColor(overall_trend)

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
          <p className="text-[14px] font-medium text-white">{agent_name}</p>
          <p className="t-caps text-white/42 mt-0.5 text-[10px]">
            {generated_at
              ? new Date(generated_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
              : ''}
            {' · '}{s.calls_analyzed || 0} calls analyzed
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TrendIcon trend={overall_trend} />
          <span className="text-[13px] font-medium" style={{ color: tc }}>
            {overall_trend ? overall_trend.charAt(0).toUpperCase() + overall_trend.slice(1) : '—'}
          </span>
        </div>
      </div>

      {/* Score row */}
      <div
        className="grid grid-cols-4 px-6 py-4 gap-4"
        style={{ borderBottom: `1px solid ${Wa(0.06)}` }}
      >
        {[
          { label: 'Avg Score',   value: s.avg_overall },
          { label: 'Resolution',  value: s.avg_resolution },
          { label: 'Pass Rate',   value: s.pass_rate != null ? `${Math.round(s.pass_rate * 100)}%` : '—' },
          { label: 'Satisfaction', value: s.avg_satisfaction != null ? `${Math.round(s.avg_satisfaction * 100)}%` : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="text-center">
            <p className="text-[16px] font-light text-white">{value ?? '—'}</p>
            <p className="t-caps text-white/42 text-[10px] mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="px-6 py-5 flex flex-col gap-5">
        {/* Strengths */}
        {strengths?.length > 0 && (
          <div>
            <p className="section-label text-[10px] mb-3">Strengths</p>
            <div className="flex flex-col gap-2">
              {strengths.map((s, i) => (
                <div key={i} className="flex items-start gap-3">
                  <CheckCircle2 size={13} color={Y} className="flex-shrink-0 mt-0.5" />
                  <p className="text-[12px] text-white/65 leading-relaxed">{s}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Improvements */}
        {improvements?.length > 0 && (
          <div>
            <p className="section-label text-[10px] mb-3">Areas to Improve</p>
            <div className="flex flex-col gap-2">
              {improvements.map((imp, i) => (
                <div key={i} className="flex items-start gap-3">
                  <AlertCircle size={13} color={Wa(0.48)} className="flex-shrink-0 mt-0.5" />
                  <p className="text-[12px] text-white/65 leading-relaxed">{imp}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action items */}
        {action_items?.length > 0 && (
          <div>
            <p className="section-label text-[10px] mb-3">Action Items</p>
            <div className="flex flex-col gap-2">
              {action_items.map((item, i) => {
                const ps = priorityStyle(item.priority)
                return (
                  <div
                    key={i}
                    className="flex items-start gap-3 rounded-xl px-4 py-3"
                    style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
                  >
                    <span
                      className="t-caps px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 text-[10px]"
                      style={{ color: ps.color, background: ps.bg, border: `1px solid ${ps.border}` }}
                    >
                      {item.priority}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] text-white/75 leading-relaxed">{item.action}</p>
                      {item.metric && (
                        <p className="t-caps text-white/38 text-[10px] mt-1">Target: {item.metric}</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Coaching note */}
        {coaching_note && (
          <div
            className="rounded-xl p-4"
            style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}
          >
            <p className="t-caps text-[10px] mb-2 flex items-center gap-1.5" style={{ color: Y }}>
              ✦ Coaching Note
            </p>
            <p className="text-[12px] text-white/65 leading-relaxed">{coaching_note}</p>
          </div>
        )}
      </div>
    </div>
  )
}
