import { useState } from 'react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function resolutionStyle(r) {
  if (r === 'resolved')   return { color: Y,        bg: Ya(0.06), border: Ya(0.18) }
  if (r === 'escalated')  return { color: Wa(0.65), bg: Wa(0.04), border: Wa(0.12) }
  return                         { color: Wa(0.38), bg: Wa(0.02), border: Wa(0.08) }
}

function fmt(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
}

export default function CallHistoryTable({ calls }) {
  const [selected, setSelected] = useState(null)

  if (!calls?.length) {
    return (
      <div
        className="rounded-2xl p-12 text-center"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <p className="t-body-14 text-white/45">No call history yet</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: `1px solid ${Wa(0.06)}` }}>
              {['Call ID', 'Prospect', 'Started', 'Duration', 'Resolution'].map(h => (
                <th key={h} className="text-left px-6 py-4">
                  <span className="section-label" style={{ fontSize: 10 }}>{h}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {calls.map((call, i) => {
              const rs = resolutionStyle(call.resolution)
              const isSelected = selected?.id === call.id
              return (
                <tr
                  key={call.id}
                  onClick={() => setSelected(isSelected ? null : call)}
                  className="cursor-pointer transition-all"
                  style={{
                    borderBottom: i < calls.length - 1 ? `1px solid ${Wa(0.04)}` : 'none',
                    background: isSelected ? Ya(0.03) : 'transparent',
                  }}
                  onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = Wa(0.02) }}
                  onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                >
                  <td className="px-6 py-4">
                    <span className="text-[13px] font-mono text-white/50">{call.id?.slice(0, 8)}</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[14px] text-white/85">
                      {call.lead_name || <span className="text-white/42">Anonymous</span>}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[13px] text-white/58">{fmt(call.started_at)}</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[13px] text-white/58 font-mono">
                      {call.duration_secs ? `${call.duration_secs}s` : '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className="t-caps px-2.5 py-1 rounded-full text-[11px]"
                      style={{ color: rs.color, background: rs.bg, border: `1px solid ${rs.border}` }}
                    >
                      {call.resolution || 'unknown'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {selected && (
        <div
          className="rounded-2xl p-5 animate-fade-in"
          style={{ background: Wa(0.025), border: `1px solid ${Ya(0.14)}` }}
        >
          <p className="section-label mb-3">Call Detail — {selected.id?.slice(0, 8)}</p>
          {selected.voice_ai_summary && (
            <p className="text-[13px] text-white/65 mb-2.5 leading-relaxed">
              <span className="text-white/85 font-medium">AI Summary: </span>
              {selected.voice_ai_summary}
            </p>
          )}
          {selected.acw_summary && (
            <p className="text-[13px] text-white/65 leading-relaxed">
              <span className="text-white/85 font-medium">ACW: </span>
              {selected.acw_summary}
            </p>
          )}
          {!selected.voice_ai_summary && !selected.acw_summary && (
            <p className="t-body-14 text-white/38">No summary available</p>
          )}
        </div>
      )}
    </div>
  )
}
