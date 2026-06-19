import { useState } from 'react'
import { PhoneCall } from 'lucide-react'
import Drawer from '../layout/Drawer.jsx'

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

function fmtDur(secs) {
  if (!secs) return '—'
  const m = Math.floor(secs / 60), s = secs % 60
  return m ? (s ? `${m}m ${s}s` : `${m}m`) : `${s}s`
}

function fmtDurShort(secs) {
  if (!secs) return '—'
  const m = Math.floor(secs / 60)
  return m > 0 ? `${m}m` : `${secs}s`
}

function CallDetail({ call }) {
  const rs       = resolutionStyle(call.resolution)
  const durColor = call.resolution === 'resolved' ? Y : Wa(0.65)
  const durGlow  = call.resolution === 'resolved' ? Ya(0.3) : 'transparent'

  const meta = [
    { label: 'Call ID',   value: call.id?.slice(0, 8), mono: true  },
    { label: 'Started',   value: fmt(call.started_at)               },
    { label: 'Duration',  value: fmtDur(call.duration_secs), mono: true },
    { label: 'Escalated', value: call.escalated ? 'Yes' : 'No'      },
  ]

  return (
    <div className="flex flex-col gap-4">

      {/* ── Main card — mirrors QAScorecard ── */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
      >
        {/* Header: name + date left · duration circle + badge right */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: `1px solid ${Wa(0.06)}` }}
        >
          <div>
            <p className="text-[14px] font-medium text-white">
              {call.customer_name || 'Unknown'}
            </p>
            <p className="t-caps text-white/42 mt-0.5 text-[10px]">
              {fmt(call.started_at)}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-[18px] font-light" style={{ color: durColor }}>
                {fmtDur(call.duration_secs)}
              </p>
              <span
                className="t-caps px-2 py-0.5 rounded-full text-[10px] inline-block mt-1"
                style={{ color: rs.color, background: rs.bg, border: `1px solid ${rs.border}` }}
              >
                {call.resolution || 'unknown'}
              </span>
            </div>

            {/* Duration circle — mirrors score circle */}
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: `${durColor}12`,
                border: `1.5px solid ${durColor}`,
                boxShadow: `0 0 12px ${durGlow}`,
              }}
            >
              <span className="text-[13px] font-semibold" style={{ color: durColor }}>
                {fmtDurShort(call.duration_secs)}
              </span>
            </div>
          </div>
        </div>

        {/* Meta rows — mirrors rubric section */}
        <div className="px-6 py-5 flex flex-col gap-3.5">
          <p className="section-label text-[10px]">Call Details</p>
          {meta.map(({ label, value, mono }) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-[12px] text-white/65">{label}</span>
              <span
                className="text-[12px] text-white/72"
                style={{ fontFamily: mono ? 'monospace' : undefined }}
              >
                {value || '—'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── AI Summary — mirrors coaching note box ── */}
      {call.voice_ai_summary ? (
        <div
          className="rounded-xl p-3.5"
          style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}
        >
          <p
            className="t-caps text-[10px] mb-1.5 flex items-center gap-1.5"
            style={{ color: Y }}
          >
            ✦ AI Summary
          </p>
          <p className="text-[12px] text-white/65 leading-relaxed">
            {call.voice_ai_summary}
          </p>
        </div>
      ) : (
        <div
          className="rounded-xl p-3.5"
          style={{ background: Wa(0.02), border: `1px solid ${Wa(0.07)}` }}
        >
          <p className="text-[12px] text-white/28">No AI summary recorded for this call.</p>
        </div>
      )}

      {/* ── ACW Note ── */}
      {call.acw_summary && (
        <div
          className="rounded-xl p-3.5"
          style={{ background: Wa(0.04), border: `1px solid ${Wa(0.10)}` }}
        >
          <p className="t-caps text-[10px] mb-1.5" style={{ color: Wa(0.42) }}>
            ACW Note
          </p>
          <p className="text-[12px] text-white/65 leading-relaxed">
            {call.acw_summary}
          </p>
        </div>
      )}

    </div>
  )
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
    <>
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: `1px solid ${Wa(0.06)}` }}>
              {['Call ID', 'Customer', 'Started', 'Duration', 'Resolution'].map(h => (
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
                  onMouseLeave={e => { e.currentTarget.style.background = isSelected ? Ya(0.03) : 'transparent' }}
                >
                  <td className="px-6 py-4">
                    <span className="text-[13px] font-mono text-white/50">{call.id?.slice(0, 8)}</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[14px] text-white/85">
                      {call.customer_name || <span className="text-white/42">Unknown</span>}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[13px] text-white/58">{fmt(call.started_at)}</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[13px] text-white/58 font-mono">{fmtDur(call.duration_secs)}</span>
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

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.customer_name || `Call ${selected?.id?.slice(0, 8)}`}
        subtitle={selected?.started_at ? fmt(selected.started_at) : undefined}
      >
        {selected && <CallDetail call={selected} />}
      </Drawer>
    </>
  )
}
