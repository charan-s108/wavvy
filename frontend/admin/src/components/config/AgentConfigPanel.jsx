import { useState, useEffect } from 'react'
import { RefreshCw, Edit3, Check, X, Cpu, Wrench, Tag } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function AgentConfigPanel({ onNavigate }) {
  const [config,        setConfig]        = useState(null)
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState(null)
  const [reloading,     setReloading]     = useState(false)
  const [toast,         setToast]         = useState(null)
  const [editingPrompt, setEditingPrompt] = useState(false)
  const [promptDraft,   setPromptDraft]   = useState('')
  const [saving,        setSaving]        = useState(false)

  async function fetchConfig() {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API}/api/tenant/config/full`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setConfig(data)
      setPromptDraft(data.voice_system_prompt || '')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchConfig() }, [])

  async function handleReload() {
    setReloading(true)
    try {
      const res = await fetch(`${API}/api/tenant/config/reload`, { method: 'POST' })
      if (!res.ok) throw new Error(`${res.status}`)
      await fetchConfig()
      showToast('Config reloaded from database')
    } catch (e) {
      showToast(`Reload failed: ${e.message}`, 'error')
    } finally {
      setReloading(false)
    }
  }

  async function handleSavePrompt() {
    setSaving(true)
    try {
      const res = await fetch(`${API}/api/tenant/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_system_prompt: promptDraft }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      setEditingPrompt(false)
      showToast('Prompt saved. Reload config to apply.')
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  function showToast(msg, type = 'success') {
    setToast({ msg, type }); setTimeout(() => setToast(null), 3500)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-3">
        <div className="w-4 h-4 rounded-full border-2 animate-spin"
          style={{ borderColor: Ya(0.3), borderTopColor: Y }} />
        <p className="text-[13px] text-white/45">Loading config…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-2xl p-5" style={{ background: Wa(0.03), border: `1px solid ${Wa(0.10)}` }}>
        <p className="text-[13px] text-white/55">Failed to load config: {error}</p>
      </div>
    )
  }

  const toolNames = config?.tool_configs
    ? Object.keys(config.tool_configs).filter(k => config.tool_configs[k]?.enabled !== false)
    : []
  const kbCols = config?.kb_collections || []

  return (
    <div className="flex flex-col gap-5 max-w-3xl">

      {/* Toast */}
      {toast && (
        <div
          className="fixed top-4 right-4 z-50 px-4 py-3 rounded-2xl text-[13px] font-medium animate-fade-in"
          style={{
            background: toast.type === 'success' ? Ya(0.10) : Wa(0.05),
            border: `1px solid ${toast.type === 'success' ? Ya(0.28) : Wa(0.12)}`,
            color: toast.type === 'success' ? Y : Wa(0.65),
          }}
        >
          {toast.msg}
        </div>
      )}

      {/* Reload button — positioned in page header via parent, but also here as standalone */}
      <div className="flex justify-end">
        <button
          onClick={handleReload}
          disabled={reloading}
          className="flex items-center gap-2 px-4 py-2 rounded-full text-[12px] font-semibold uppercase tracking-wider transition-all disabled:opacity-50"
          style={{ background: Ya(0.08), border: `1px solid ${Ya(0.22)}`, color: Y }}
          onMouseEnter={e => { if (!reloading) e.currentTarget.style.background = Ya(0.14) }}
          onMouseLeave={e => e.currentTarget.style.background = Ya(0.08)}
        >
          <RefreshCw size={12} className={reloading ? 'animate-spin' : ''} />
          {reloading ? 'Reloading…' : 'Reload Config'}
        </button>
      </div>

      {/* Active agent identity */}
      <div
        className="rounded-2xl p-5 flex flex-col gap-4"
        style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
      >
        <div className="flex items-center gap-2">
          <Cpu size={13} color={Y} />
          <p className="section-label text-[10px]">Active Agent</p>
        </div>
        <div className="flex items-center gap-4">
          <div
            className="w-11 h-11 rounded-full flex items-center justify-center text-[14px] font-bold flex-shrink-0"
            style={{ background: Ya(0.08), border: `1px solid ${Ya(0.22)}`, color: Y }}
          >
            {(config?.agent_name || 'A')[0]}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[14px] font-medium text-white">{config?.agent_name}</p>
            <p className="text-[12px] text-white/48 mt-0.5">
              {config?.industry || 'general'} · {config?.tenant_id}
            </p>
          </div>
          <span
            className="t-caps px-2.5 py-1 rounded-full text-[10px] flex-shrink-0"
            style={{ background: Ya(0.08), border: `1px solid ${Ya(0.22)}`, color: Y }}
          >
            ACTIVE
          </span>
        </div>
      </div>

      {/* Tools */}
      <div
        className="rounded-2xl p-5"
        style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Wrench size={13} color={Y} />
          <p className="section-label text-[10px]">Enabled Tools</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {toolNames.length ? toolNames.map(name => (
            <span
              key={name}
              className="px-3 py-1.5 rounded-full t-caps text-[10px]"
              style={{ background: Ya(0.06), border: `1px solid ${Ya(0.18)}`, color: Ya(0.85) }}
            >
              {name.replace(/_/g, ' ')}
            </span>
          )) : (
            <p className="text-[13px] text-white/40">No tools configured</p>
          )}
        </div>
      </div>

      {/* Support categories + KB */}
      <div className="grid grid-cols-2 gap-4">
        <div
          className="rounded-2xl p-5"
          style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
        >
          <div className="flex items-center gap-2 mb-3.5">
            <Tag size={12} color={Wa(0.45)} />
            <p className="section-label text-[10px]">Support Categories</p>
          </div>
          <div className="flex flex-col gap-1.5">
            {(config?.support_categories || []).map(c => (
              <p key={c} className="text-[12px] text-white/62 capitalize">{c.replace(/_/g, ' ')}</p>
            ))}
          </div>
        </div>

        <div
          className="rounded-2xl p-5"
          style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
        >
          <div className="flex items-center gap-2 mb-3.5">
            <Tag size={12} color={Y} />
            <p className="section-label text-[10px]">KB Collections</p>
          </div>
          <div className="flex flex-col gap-1.5">
            {kbCols.length ? kbCols.map(c => (
              <span key={c}
                className="text-[12px] px-2.5 py-1 rounded-full self-start"
                style={{ background: Ya(0.06), border: `1px solid ${Ya(0.16)}`, color: Ya(0.85) }}
              >
                {c}
              </span>
            )) : (
              <p className="text-[12px] text-white/38">None</p>
            )}
          </div>
        </div>
      </div>

      {/* Voice system prompt */}
      <div
        className="rounded-2xl p-5 flex flex-col gap-4"
        style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
      >
        <div className="flex items-center justify-between">
          <p className="section-label text-[10px]">Voice System Prompt</p>
          <button
            onClick={() => onNavigate && onNavigate('prompts')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all"
            style={{ background: Ya(0.10), border: `1px solid ${Ya(0.28)}`, color: Y }}
          >
            <Edit3 size={11} /> Edit in Prompt Studio →
          </button>
        </div>
        <pre
          className="rounded-xl p-4 overflow-x-auto"
          style={{
            background: Wa(0.02),
            border: `1px solid ${Wa(0.07)}`,
            color: Wa(0.55),
            fontFamily: 'monospace',
            fontSize: 11,
            lineHeight: 1.65,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: 200,
            overflowY: 'auto',
          }}
        >
          {config?.voice_system_prompt ? config.voice_system_prompt.slice(0, 300) + (config.voice_system_prompt.length > 300 ? '…' : '') : '(empty)'}
        </pre>
      </div>

    </div>
  )
}
