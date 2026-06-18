import { useState } from 'react'
import { X, Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'

const Y = '#f4f73d'

const NODE_TYPES  = ['collect', 'inform', 'action', 'branch', 'end']
const SLOT_TYPES  = ['phone', 'otp', 'txn_id', 'text', 'bool', 'email']
const ALL_TOOLS   = [
  'verify_account', 'send_otp', 'verify_otp',
  'lookup_transaction', 'search_transactions', 'check_payment_status',
  'get_account_holds', 'get_refund_status', 'get_dispute_status',
  'unlock_account', 'initiate_refund', 'raise_dispute', 'report_fraud',
  'escalate_to_human', 'capture_lead', 'schedule_demo', 'cancel_demo',
]
const BIZ_TOOLS   = ['verify_account', 'send_otp', 'verify_otp', 'initiate_refund',
                     'unlock_account', 'raise_dispute', 'report_fraud', 'escalate_to_human']

export default function NodeConfigPanel({ node, allNodeIds, onUpdate, onDelete, onClose }) {
  const [showPersona, setShowPersona] = useState(false)

  if (!node) return null

  function field(key, value) { onUpdate(node.id, { [key]: value }) }

  function toggleTool(tool) {
    const set = new Set(node.allowed_tools || [])
    set.has(tool) ? set.delete(tool) : set.add(tool)
    field('allowed_tools', [...set])
  }

  function addEdge() {
    field('edges', [...(node.edges || []), { condition: 'success', target_node_id: '' }])
  }
  function updateEdge(i, patch) {
    const edges = [...(node.edges || [])]
    edges[i] = { ...edges[i], ...patch }
    field('edges', edges)
  }
  function removeEdge(i) {
    field('edges', (node.edges || []).filter((_, j) => j !== i))
  }

  function addVariable() {
    const name = `slot_${Date.now()}`
    field('variables', { ...(node.variables || {}), [name]: { type: 'text', required: true, min_length: null } })
  }
  function removeVariable(k) {
    const v = { ...(node.variables || {}) }; delete v[k]; field('variables', v)
  }
  function updateVariable(k, patch) {
    field('variables', { ...(node.variables || {}), [k]: { ...(node.variables || {})[k], ...patch } })
  }

  function updatePersona(patch) {
    field('agent_profile', { ...(node.agent_profile || { name: '', persona: '', response_style: 'medium' }), ...patch })
  }

  const S = { // label style
    label: { color: '#727781', fontSize: 11, marginBottom: 3, display: 'block' },
    input: {
      width: '100%', boxSizing: 'border-box',
      background: '#10131c', color: '#fff',
      border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
      padding: '6px 9px', fontSize: 12, outline: 'none',
    },
    section: { marginBottom: 18 },
    row: { display: 'flex', gap: 8, marginBottom: 8 },
  }

  return (
    <div style={{
      width: 320, flexShrink: 0, borderLeft: '1px solid rgba(255,255,255,0.08)',
      overflowY: 'auto', padding: '16px 14px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ color: '#fff', fontWeight: 600, fontSize: 14 }}>Node Config</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => onDelete(node.id)} style={{
            background: 'rgba(252,83,91,0.12)', border: 'none', borderRadius: 6,
            color: '#fc535b', cursor: 'pointer', padding: '4px 8px', fontSize: 11,
          }}><Trash2 size={11}/></button>
          <button onClick={onClose} style={{
            background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: 6,
            color: '#b2b2b4', cursor: 'pointer', padding: '4px 8px',
          }}><X size={13}/></button>
        </div>
      </div>

      {/* Name */}
      <div style={S.section}>
        <label style={S.label}>Name</label>
        <input style={S.input} value={node.name || ''} onChange={e => field('name', e.target.value)} />
      </div>

      {/* Type */}
      <div style={S.section}>
        <label style={S.label}>Node Type</label>
        <select style={{ ...S.input }} value={node.node_type || 'collect'} onChange={e => field('node_type', e.target.value)}>
          {NODE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {/* Directive */}
      <div style={S.section}>
        <label style={S.label}>Directive (injected into LLM)</label>
        <textarea rows={3} style={{ ...S.input, resize: 'vertical' }}
          value={node.directive || ''} onChange={e => field('directive', e.target.value)} />
      </div>

      {/* Allowed Tools */}
      <div style={S.section}>
        <label style={S.label}>Allowed Tools (LLM-callable)</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {ALL_TOOLS.map(t => {
            const on = (node.allowed_tools || []).includes(t)
            return (
              <button key={t} onClick={() => toggleTool(t)} style={{
                padding: '3px 8px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
                background: on ? 'rgba(244,247,61,0.15)' : 'rgba(255,255,255,0.05)',
                color: on ? Y : '#727781',
                border: `1px solid ${on ? 'rgba(244,247,61,0.3)' : 'rgba(255,255,255,0.08)'}`,
              }}>{t}</button>
            )
          })}
        </div>
      </div>

      {/* Auto Actions */}
      <div style={S.section}>
        <label style={S.label}>Auto-Action (orchestrator fires on slot complete)</label>
        <select style={{ ...S.input }}
          value={(node.auto_actions || [])[0] || ''}
          onChange={e => field('auto_actions', e.target.value ? [e.target.value] : [])}>
          <option value="">— none —</option>
          {BIZ_TOOLS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {/* Variables / Slots */}
      <div style={S.section}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={{ ...S.label, marginBottom: 0 }}>Slots (required variables)</label>
          <button onClick={addVariable} style={{
            background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: 5,
            cursor: 'pointer', color: '#b2b2b4', padding: '2px 7px', fontSize: 11,
          }}><Plus size={10}/> add</button>
        </div>
        {Object.entries(node.variables || {}).map(([k, v]) => (
          <div key={k} style={{ ...S.row, alignItems: 'center' }}>
            <input style={{ ...S.input, width: 90 }} value={k} readOnly />
            <select style={{ ...S.input, width: 90 }} value={v.type || 'text'}
              onChange={e => updateVariable(k, { type: e.target.value })}>
              {SLOT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <label style={{ color: '#b2b2b4', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={!!v.required}
                onChange={e => updateVariable(k, { required: e.target.checked })} />req
            </label>
            <button onClick={() => removeVariable(k)} style={{
              background: 'none', border: 'none', cursor: 'pointer', color: '#fc535b', padding: 2,
            }}><X size={12}/></button>
          </div>
        ))}
      </div>

      {/* Edges */}
      <div style={S.section}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={{ ...S.label, marginBottom: 0 }}>Edges</label>
          <button onClick={addEdge} style={{
            background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: 5,
            cursor: 'pointer', color: '#b2b2b4', padding: '2px 7px', fontSize: 11,
          }}><Plus size={10}/> add</button>
        </div>
        {(node.edges || []).map((e, i) => (
          <div key={i} style={{ ...S.row }}>
            <input style={{ ...S.input, width: 100 }} value={e.condition || ''} placeholder="condition"
              onChange={ev => updateEdge(i, { condition: ev.target.value })} />
            <select style={{ ...S.input, flex: 1 }} value={e.target_node_id || ''}
              onChange={ev => updateEdge(i, { target_node_id: ev.target.value })}>
              <option value="">— target —</option>
              <option value="__end__">__end__</option>
              {allNodeIds.filter(id => id !== node.id).map(id => <option key={id} value={id}>{id}</option>)}
            </select>
            <button onClick={() => removeEdge(i)} style={{
              background: 'none', border: 'none', cursor: 'pointer', color: '#fc535b', padding: 2,
            }}><X size={12}/></button>
          </div>
        ))}
      </div>

      {/* Max Attempts */}
      <div style={{ ...S.section, display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={S.label}>Max Attempts</label>
          <input type="number" min={1} max={20} style={S.input}
            value={node.max_attempts || 3} onChange={e => field('max_attempts', Number(e.target.value))} />
        </div>
        <div style={{ flex: 1 }}>
          <label style={S.label}>Timeout Edge</label>
          <input style={S.input} value={node.on_timeout_edge || ''}
            onChange={e => field('on_timeout_edge', e.target.value || null)} placeholder="e.g. timeout" />
        </div>
      </div>

      {/* Agent Persona */}
      <div style={S.section}>
        <button onClick={() => setShowPersona(v => !v)} style={{
          background: 'none', border: 'none', cursor: 'pointer', color: '#b2b2b4',
          fontSize: 12, padding: 0, display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8,
        }}>
          {showPersona ? <ChevronDown size={13}/> : <ChevronRight size={13}/>} Agent Persona
        </button>
        {showPersona && (
          <>
            <label style={S.label}>Name</label>
            <input style={{ ...S.input, marginBottom: 8 }}
              value={node.agent_profile?.name || ''}
              onChange={e => updatePersona({ name: e.target.value })} placeholder="e.g. Fraud Specialist" />
            <label style={S.label}>Persona (appended to system prompt)</label>
            <textarea rows={3} style={{ ...S.input, resize: 'vertical', marginBottom: 8 }}
              value={node.agent_profile?.persona || ''}
              onChange={e => updatePersona({ persona: e.target.value })} />
            <label style={S.label}>Response Style</label>
            <select style={S.input} value={node.agent_profile?.response_style || 'medium'}
              onChange={e => updatePersona({ response_style: e.target.value })}>
              <option value="brief">brief</option>
              <option value="medium">medium</option>
              <option value="detailed">detailed</option>
            </select>
          </>
        )}
      </div>
    </div>
  )
}
