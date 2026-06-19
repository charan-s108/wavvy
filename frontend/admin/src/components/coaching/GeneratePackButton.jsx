import { useState } from 'react'
import { Sparkles, Loader } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function GeneratePackButton({ agentId, scoredCalls, onGenerated }) {
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const canGenerate = scoredCalls >= 3

  async function handleGenerate() {
    if (!canGenerate || loading) return
    setLoading(true); setError(null)
    try {
      const resp = await fetch(`${API}/api/coaching/generate/${agentId}`, { method: 'POST' })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body.detail || `Error ${resp.status}`)
      }
      onGenerated(await resp.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-1.5 items-end">
      <button
        onClick={handleGenerate}
        disabled={!canGenerate || loading}
        className="flex items-center gap-2 px-4 py-2 rounded-full text-[12px] font-semibold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: canGenerate ? Y : Wa(0.05),
          color:      canGenerate ? '#000' : Wa(0.38),
          border:     canGenerate ? 'none' : `1px solid ${Wa(0.10)}`,
        }}
        onMouseEnter={e => { if (canGenerate && !loading) e.currentTarget.style.opacity = '0.88' }}
        onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
      >
        {loading
          ? <Loader size={13} className="animate-spin" />
          : <Sparkles size={13} />
        }
        {loading ? 'Generating…' : 'Generate'}
      </button>
      {!canGenerate && (
        <p className="t-caps text-white/35 text-[10px]">
          Requires {3 - scoredCalls} more scored call{3 - scoredCalls !== 1 ? 's' : ''}
        </p>
      )}
      {error && (
        <p className="t-caps text-white/45 text-[10px]">{error}</p>
      )}
    </div>
  )
}
