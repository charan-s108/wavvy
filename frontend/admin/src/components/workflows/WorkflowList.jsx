import { useState, useEffect } from 'react'
import { Plus, Zap, ZapOff } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const Y   = '#f4f73d'

export default function WorkflowList({ activeId, onSelect, onNew }) {
  const [workflows, setWorkflows] = useState([])
  const [loading,   setLoading]   = useState(true)

  async function load() {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/workflows`)
      if (res.ok) setWorkflows(await res.json())
    } catch {}
    setLoading(false)
  }

  async function toggle(wf, e) {
    e.stopPropagation()
    const url = wf.is_active
      ? `${API}/api/workflows/${wf.id}`
      : `${API}/api/workflows/${wf.id}/activate`
    const method = wf.is_active ? 'DELETE' : 'POST'
    await fetch(url, { method })
    load()
  }

  useEffect(() => { load() }, [])

  return (
    <div style={{ width: 220, borderRight: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ color: '#b2b2b4', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 }}>Workflows</span>
        <button onClick={onNew} style={{
          width: 24, height: 24, borderRadius: '50%', background: Y,
          border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Plus size={14} color="#000" />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && <p style={{ color: '#727781', fontSize: 12, padding: '0 14px' }}>Loading…</p>}
        {workflows.map(wf => (
          <div key={wf.id} onClick={() => onSelect(wf.id)} style={{
            padding: '8px 14px', cursor: 'pointer',
            background: activeId === wf.id ? 'rgba(244,247,61,0.08)' : 'transparent',
            borderLeft: activeId === wf.id ? `2px solid ${Y}` : '2px solid transparent',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: activeId === wf.id ? Y : '#fff', fontSize: 13, fontWeight: 500,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {wf.name}
              </div>
              <div style={{ color: '#727781', fontSize: 11, marginTop: 2 }}>
                {wf.node_count} node{wf.node_count !== 1 ? 's' : ''} · v{wf.version}
              </div>
            </div>
            <button onClick={e => toggle(wf, e)} title={wf.is_active ? 'Deactivate' : 'Activate'}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 0 0 6px', flexShrink: 0 }}>
              {wf.is_active
                ? <Zap size={13} color="#1D9E75" />
                : <ZapOff size={13} color="#727781" />}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
