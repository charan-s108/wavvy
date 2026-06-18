import { Phone, Loader } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function OrchestratorBadge({ call }) {
  const mode = call.orchestrator_mode || 'general'
  if (mode === 'escalation') {
    return (
      <span style={{ padding: '2px 8px', borderRadius: 5, background: 'rgba(252,83,91,0.15)', color: '#fc535b', fontSize: 11 }}>
        Escalating
      </span>
    )
  }
  if (mode === 'workflow') {
    const label = [call.active_workflow, call.active_node].filter(Boolean).join(' · ')
    return (
      <span style={{ padding: '2px 8px', borderRadius: 5, background: 'rgba(244,247,61,0.12)', color: '#f4f73d', fontSize: 11 }}>
        ▸ {label || 'Workflow'}
      </span>
    )
  }
  return (
    <span style={{ padding: '2px 8px', borderRadius: 5, background: 'rgba(255,255,255,0.05)', color: '#727781', fontSize: 11 }}>
      General
    </span>
  )
}

function elapsed(started) {
  if (!started) return '—'
  const secs = Math.floor((Date.now() - new Date(started).getTime()) / 1000)
  const m = Math.floor(secs / 60), s = secs % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function LiveCallsTable({ liveCalls, loading }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-3">
        <Loader size={16} color={Wa(0.35)} className="animate-spin" />
        <span className="t-body-14 text-white/45">Loading…</span>
      </div>
    )
  }

  if (!liveCalls?.length) {
    return (
      <div
        className="rounded-2xl p-16 flex flex-col items-center justify-center gap-4"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: Wa(0.03), border: `1px solid ${Wa(0.07)}` }}
        >
          <Phone size={20} color={Wa(0.35)} />
        </div>
        <p className="t-body-14 text-white/45">No active calls right now</p>
      </div>
    )
  }

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
    >
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: `1px solid ${Wa(0.06)}` }}>
            {['Call ID', 'Mode', 'Stage', 'Intent', 'Duration', 'Status'].map(h => (
              <th key={h} className="text-left px-6 py-4">
                <span className="section-label" style={{ fontSize: 10 }}>{h}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {liveCalls.map((call, i) => (
            <tr
              key={call.call_id}
              style={{ borderBottom: i < liveCalls.length - 1 ? `1px solid ${Wa(0.04)}` : 'none' }}
            >
              <td className="px-6 py-4">
                <span className="text-[13px] font-mono text-white/50">{call.call_id?.slice(0, 8)}</span>
              </td>
              <td className="px-6 py-4">
                <OrchestratorBadge call={call} />
              </td>
              <td className="px-6 py-4">
                <span className="text-[14px] text-white/80">{call.stage || 'voice_ai'}</span>
              </td>
              <td className="px-6 py-4">
                <span className="t-caps text-white/52 text-[11px]">
                  {call.intent ? call.intent.replace(/_/g, ' ') : '—'}
                </span>
              </td>
              <td className="px-6 py-4">
                <span className="text-[14px] text-white/65 font-mono">{elapsed(call.started_at)}</span>
              </td>
              <td className="px-6 py-4">
                <div className="flex items-center gap-2">
                  <span
                    className="w-1.5 h-1.5 rounded-full call-pulse"
                    style={{ background: Y }}
                  />
                  <span className="t-caps text-[11px]" style={{ color: Y }}>active</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
