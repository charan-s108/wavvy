import { useState } from 'react'
import { Plus, X, Zap } from 'lucide-react'

const Y = '#f4f73d'

export default function WorkflowIntentPanel({ workflow, onUpdate }) {
  const [newExample, setNewExample] = useState('')

  if (!workflow) return null

  const examples = workflow.few_shot_examples || []

  function addExample() {
    if (!newExample.trim()) return
    onUpdate({ few_shot_examples: [...examples, newExample.trim()] })
    setNewExample('')
  }
  function removeExample(i) {
    onUpdate({ few_shot_examples: examples.filter((_, j) => j !== i) })
  }

  const S = {
    label: { color: '#727781', fontSize: 11, marginBottom: 4, display: 'block' },
    input: {
      background: '#10131c', color: '#fff',
      border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
      padding: '6px 9px', fontSize: 12, outline: 'none', width: '100%', boxSizing: 'border-box',
    },
  }

  return (
    <div style={{
      borderTop: '1px solid rgba(255,255,255,0.08)',
      padding: '14px 16px', background: '#10131c',
    }}>
      <div style={{ display: 'flex', gap: 20 }}>
        {/* Intent Definition */}
        <div style={{ flex: 2 }}>
          <label style={S.label}>Intent Definition (natural language)</label>
          <textarea rows={2} style={{ ...S.input, resize: 'none' }}
            value={workflow.intent_definition || ''}
            placeholder="Customer needs help with a transaction, refund…"
            onChange={e => onUpdate({ intent_definition: e.target.value })} />
        </div>

        {/* Few-shot examples */}
        <div style={{ flex: 3 }}>
          <label style={S.label}>Few-Shot Examples (embedded at save)</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
            {examples.map((ex, i) => (
              <span key={i} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '3px 8px', borderRadius: 5,
                background: 'rgba(244,247,61,0.1)', color: Y, fontSize: 11,
              }}>
                {ex}
                <button onClick={() => removeExample(i)} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#727781', padding: 0, lineHeight: 1,
                }}><X size={10}/></button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input style={{ ...S.input, flex: 1 }}
              value={newExample}
              placeholder="Add example utterance…"
              onChange={e => setNewExample(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addExample()} />
            <button onClick={addExample} style={{
              padding: '5px 12px', borderRadius: 6, background: 'rgba(255,255,255,0.08)',
              color: '#b2b2b4', border: 'none', cursor: 'pointer', fontSize: 12,
            }}><Plus size={12}/></button>
          </div>
        </div>

        {/* Threshold */}
        <div style={{ width: 140 }}>
          <label style={S.label}>Intent Threshold: {(workflow.intent_threshold || 0.72).toFixed(2)}</label>
          <input type="range" min={0.50} max={0.95} step={0.01}
            value={workflow.intent_threshold || 0.72}
            onChange={e => onUpdate({ intent_threshold: parseFloat(e.target.value) })}
            style={{ width: '100%' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#727781', fontSize: 10, marginTop: 2 }}>
            <span>0.50 (loose)</span><span>0.95 (strict)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
