import { useState, useEffect, useCallback } from 'react'
import { CheckCircle2, XCircle, RefreshCw, Zap } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const Wa  = (a) => `rgba(255,255,255,${a})`
const Y   = '#f4f73d'

function timeAgo(isoStr) {
  if (!isoStr) return '—'
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (diff < 60)   return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(isoStr).toLocaleDateString()
}

export default function RecentActionsPanel() {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchActions = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/orchestration/recent-actions?limit=20`)
      if (resp.ok) setActions(await resp.json())
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { fetchActions() }, [fetchActions])

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: `1px solid ${Wa(0.06)}` }}
      >
        <div className="flex items-center gap-2">
          <Zap size={14} style={{ color: Y }} />
          <span className="section-label" style={{ fontSize: 11 }}>Recent HITL Actions</span>
        </div>
        <button
          onClick={fetchActions}
          className="flex items-center gap-1.5 text-[11px] transition-opacity hover:opacity-70"
          style={{ background: 'none', border: 'none', color: Wa(0.45), cursor: 'pointer' }}
        >
          <RefreshCw size={11} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10">
          <RefreshCw size={14} color={Wa(0.3)} className="animate-spin" />
        </div>
      ) : actions.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-10">
          <Zap size={20} color={Wa(0.15)} />
          <p className="t-body-14 text-white/35">No HITL actions recorded yet</p>
        </div>
      ) : (
        <div className="divide-y" style={{ borderColor: Wa(0.04) }}>
          {actions.map((a) => (
            <div key={a.id} className="flex items-center gap-4 px-5 py-3.5">
              {/* Status icon */}
              <div className="flex-shrink-0">
                {a.success
                  ? <CheckCircle2 size={15} style={{ color: '#1D9E75' }} />
                  : <XCircle     size={15} style={{ color: '#fc535b' }} />
                }
              </div>

              {/* Action + call */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-white truncate">
                    {a.action.replace(/_/g, ' ')}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-md font-mono flex-shrink-0"
                    style={{ background: Wa(0.05), color: Wa(0.45) }}
                  >
                    {a.call_id?.slice(0, 8)}
                  </span>
                </div>
                <p className="text-[11px] mt-0.5" style={{ color: Wa(0.38) }}>
                  approved by {a.approved_by}
                  {a.result?.message && ` · ${String(a.result.message).slice(0, 60)}`}
                </p>
              </div>

              {/* Time */}
              <span className="text-[11px] flex-shrink-0" style={{ color: Wa(0.3) }}>
                {timeAgo(a.created_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
