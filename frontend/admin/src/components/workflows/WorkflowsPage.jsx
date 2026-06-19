import { useState } from 'react'
import { Save, Plus } from 'lucide-react'
import WorkflowList         from './WorkflowList'
import WorkflowCanvas       from './WorkflowCanvas'
import NodeConfigPanel      from './NodeConfigPanel'
import WorkflowIntentPanel  from './WorkflowIntentPanel'
import { useWorkflowEditor } from './useWorkflowEditor'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const Y   = '#f4f73d'

function newWorkflowTemplate() {
  return {
    id:                null,
    name:              'New Workflow',
    description:       '',
    intent_definition: '',
    few_shot_examples: [],
    intent_threshold:  0.72,
    is_active:         false,
    definition: {
      id:           null,
      entry_node_id: 'start',
      nodes: {
        start: {
          id: 'start', name: 'Start', node_type: 'collect',
          directive: '', allowed_tools: [], auto_actions: [],
          variables: {}, completion_condition: '',
          edges: [], max_attempts: 3, on_timeout_edge: null, agent_profile: null,
        },
      },
    },
  }
}

export default function WorkflowsPage() {
  const [listKey,    setListKey]    = useState(0)  // bump to reload list
  const [activeWfId, setActiveWfId] = useState(null)
  const ed = useWorkflowEditor(null)

  async function selectWorkflow(id) {
    setActiveWfId(id)
    try {
      const res = await fetch(`${API}/api/workflows/${id}`)
      if (res.ok) {
        const data = await res.json()
        ed.loadWorkflow(data)
      }
    } catch {}
  }

  function newWorkflow() {
    setActiveWfId(null)
    ed.loadWorkflow(newWorkflowTemplate())
  }

  async function handleSave() {
    await ed.save()
    setListKey(k => k + 1)
  }

  const nodes     = ed.workflow?.definition?.nodes || {}
  const nodeIds   = Object.keys(nodes)
  const selNode   = ed.selected ? nodes[ed.selected] : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: '#14131d', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0, color: '#fff', fontSize: 18, fontWeight: 600 }}>Workflow Builder</h2>
          {ed.workflow && (
            <>
              <span style={{ color: '#727781', fontSize: 13 }}>·</span>
              <input
                value={ed.workflow.name || ''}
                onChange={e => ed.updateIntent({ name: e.target.value })}
                style={{
                  background: 'transparent', color: '#fff', border: 'none', outline: 'none',
                  fontSize: 14, fontWeight: 500,
                }}
              />
              {ed.dirty && <span style={{ color: Y, fontSize: 11 }}>unsaved</span>}
            </>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {ed.error && <span style={{ color: '#fc535b', fontSize: 12 }}>{ed.error}</span>}
          {ed.workflow && (
            <>
              <button onClick={ed.addNode} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 14px', borderRadius: 6,
                background: 'rgba(255,255,255,0.08)', color: '#b2b2b4',
                border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', fontSize: 12,
              }}>
                <Plus size={12}/> Add Node
              </button>
              <button onClick={handleSave} disabled={!ed.dirty || ed.saving} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 14px', borderRadius: 6,
                background: ed.dirty ? Y : 'rgba(244,247,61,0.3)',
                color: '#000', border: 'none', cursor: ed.dirty ? 'pointer' : 'not-allowed',
                fontWeight: 600, fontSize: 12,
              }}>
                <Save size={12}/>{ed.saving ? 'Saving…' : 'Save'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Main area */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <WorkflowList
          key={listKey}
          activeId={activeWfId}
          onSelect={selectWorkflow}
          onNew={newWorkflow}
        />

        {/* Canvas + bottom intent panel */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <WorkflowCanvas
            workflow={ed.workflow}
            positions={ed.positions}
            selected={ed.selected}
            onSelect={ed.setSelected}
            onMove={ed.moveNode}
          />
          <WorkflowIntentPanel
            workflow={ed.workflow}
            onUpdate={ed.updateIntent}
          />
        </div>

        {/* Node config panel (right side) */}
        {selNode && (
          <NodeConfigPanel
            node={selNode}
            allNodeIds={nodeIds}
            onUpdate={ed.updateNode}
            onDelete={ed.deleteNode}
            onClose={() => ed.setSelected(null)}
          />
        )}
      </div>
    </div>
  )
}
