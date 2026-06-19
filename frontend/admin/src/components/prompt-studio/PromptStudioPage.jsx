import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import PromptEditor from './PromptEditor'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const Y   = '#f4f73d'

const TABS = [
  { key: 'voice_system_prompt',      label: 'Voice Agent'      },
  { key: 'context_prompt',           label: 'Context'          },
  { key: 'companion_mid_call_prompt', label: 'Companion (live)' },
  { key: 'companion_acw_prompt',     label: 'Companion (ACW)'  },
  { key: 'qa_prompt',                label: 'QA Evaluator'     },
  { key: 'coaching_prompt',          label: 'Coaching'         },
]

export default function PromptStudioPage() {
  const [activeTab, setActiveTab] = useState(TABS[0].key)
  const [prompts,   setPrompts]   = useState({})
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [reloading, setReloading] = useState(false)

  async function fetchConfig() {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API}/api/tenant/config/full`)
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      const extracted = {}
      TABS.forEach(t => { extracted[t.key] = data[t.key] || '' })
      setPrompts(extracted)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function reloadAgent() {
    setReloading(true)
    try {
      await fetch(`${API}/api/tenant/config/reload`, { method: 'POST' })
    } catch {}
    setReloading(false)
  }

  useEffect(() => { fetchConfig() }, [])

  function handleChange(key, val) {
    setPrompts(p => ({ ...p, [key]: val }))
  }

  return (
    <div style={{ padding: '28px 32px', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, color: '#fff', fontSize: 20, fontWeight: 600 }}>Prompt Studio</h2>
          <p style={{ margin: '4px 0 0', color: '#727781', fontSize: 13 }}>
            Edit system prompts for all agents. Changes take effect on next call after Reload.
          </p>
        </div>
        <button onClick={reloadAgent} disabled={reloading} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '7px 16px', borderRadius: 7,
          background: reloading ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.08)',
          color: '#b2b2b4', border: '1px solid rgba(255,255,255,0.1)',
          cursor: reloading ? 'not-allowed' : 'pointer', fontSize: 13,
        }}>
          <RefreshCw size={13} style={{ animation: reloading ? 'spin 1s linear infinite' : 'none' }} />
          {reloading ? 'Reloading…' : 'Reload Agent'}
        </button>
      </div>

      {loading && <p style={{ color: '#727781' }}>Loading prompts…</p>}
      {error   && <p style={{ color: '#fc535b' }}>Error: {error}</p>}

      {!loading && !error && (
        <div style={{ display: 'flex', flex: 1, gap: 0, overflow: 'hidden' }}>
          {/* Tab list */}
          <div style={{
            width: 180, flexShrink: 0, borderRight: '1px solid rgba(255,255,255,0.08)',
            paddingRight: 0, display: 'flex', flexDirection: 'column', gap: 2,
          }}>
            {TABS.map(tab => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
                textAlign: 'left', padding: '9px 16px', borderRadius: 7,
                background: activeTab === tab.key ? 'rgba(244,247,61,0.1)' : 'transparent',
                color: activeTab === tab.key ? Y : '#b2b2b4',
                border: 'none', cursor: 'pointer', fontSize: 13,
                borderRight: activeTab === tab.key ? `2px solid ${Y}` : '2px solid transparent',
              }}>{tab.label}</button>
            ))}
          </div>

          {/* Editor area */}
          <div style={{ flex: 1, paddingLeft: 24, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {TABS.filter(t => t.key === activeTab).map(tab => (
              <PromptEditor
                key={tab.key}
                promptKey={tab.key}
                label={tab.label}
                value={prompts[tab.key] || ''}
                onChange={val => handleChange(tab.key, val)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
