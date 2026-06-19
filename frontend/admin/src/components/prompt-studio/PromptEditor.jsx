import { useState } from 'react'
import { Save, RotateCcw, CheckCircle } from 'lucide-react'
import PromptVariableHints from './PromptVariableHints'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const Y   = '#f4f73d'
const B   = '#1b1d2a'

function tokenEst(text) { return Math.ceil((text || '').length / 4) }

export default function PromptEditor({ promptKey, label, value, onChange }) {
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const [error,   setError]   = useState(null)

  const dirty = value !== (onChange._original || value)

  async function handleSave() {
    setSaving(true); setError(null); setSaved(false)
    try {
      const res = await fetch(`${API}/api/tenant/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [promptKey]: value }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ color: '#b2b2b4', fontSize: 12 }}>
          {tokenEst(value)} tokens est. · {(value || '').length} chars
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          {saved && (
            <span style={{ color: '#1D9E75', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <CheckCircle size={13}/> Saved
            </span>
          )}
          {error && <span style={{ color: '#fc535b', fontSize: 12 }}>{error}</span>}
          <button onClick={handleSave} disabled={saving} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 14px', borderRadius: 6,
            background: saving ? 'rgba(244,247,61,0.3)' : Y,
            color: '#000', border: 'none', cursor: saving ? 'not-allowed' : 'pointer',
            fontWeight: 600, fontSize: 12,
          }}>
            <Save size={12}/>{saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <textarea
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        spellCheck={false}
        style={{
          flex: 1, minHeight: 340, width: '100%', boxSizing: 'border-box',
          background: '#10131c', color: '#fff',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 8, padding: '12px 14px',
          fontFamily: 'monospace', fontSize: 13, lineHeight: 1.6,
          resize: 'vertical', outline: 'none',
        }}
      />

      <PromptVariableHints promptKey={promptKey} />
    </div>
  )
}
