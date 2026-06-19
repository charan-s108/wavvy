import { useState, useCallback } from 'react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || ''

const NODE_DEFAULTS = () => ({
  id:                   `node_${Date.now()}`,
  name:                 'New Node',
  node_type:            'collect',
  directive:            '',
  allowed_tools:        [],
  auto_actions:         [],
  variables:            {},
  completion_condition: '',
  edges:                [],
  max_attempts:         3,
  on_timeout_edge:      null,
  agent_profile:        null,
})

export function useWorkflowEditor(initialWorkflow) {
  const [workflow,  setWorkflow]  = useState(initialWorkflow || null)
  const [positions, setPositions] = useState({})   // node_id → {x, y}
  const [selected,  setSelected]  = useState(null)  // node_id
  const [dirty,     setDirty]     = useState(false)
  const [saving,    setSaving]    = useState(false)
  const [error,     setError]     = useState(null)

  function loadWorkflow(wf, pos = null) {
    setWorkflow(wf)
    setDirty(false)
    setSelected(null)
    if (pos) {
      setPositions(pos)
    } else {
      // Auto-layout: column × row grid
      const ids = Object.keys(wf.definition?.nodes || {})
      const cols = 3
      const auto = {}
      ids.forEach((id, i) => {
        auto[id] = { x: (i % cols) * 260 + 40, y: Math.floor(i / cols) * 180 + 40 }
      })
      setPositions(auto)
    }
  }

  function addNode() {
    const n = NODE_DEFAULTS()
    const ids = Object.keys(workflow.definition.nodes)
    const maxX = ids.reduce((m, id) => Math.max(m, (positions[id]?.x || 0)), 0)
    setWorkflow(wf => ({
      ...wf,
      definition: {
        ...wf.definition,
        nodes: { ...wf.definition.nodes, [n.id]: n },
      },
    }))
    setPositions(p => ({ ...p, [n.id]: { x: maxX + 280, y: 40 } }))
    setSelected(n.id)
    setDirty(true)
  }

  function updateNode(nodeId, patch) {
    setWorkflow(wf => ({
      ...wf,
      definition: {
        ...wf.definition,
        nodes: {
          ...wf.definition.nodes,
          [nodeId]: { ...wf.definition.nodes[nodeId], ...patch },
        },
      },
    }))
    setDirty(true)
  }

  function deleteNode(nodeId) {
    setWorkflow(wf => {
      const nodes = { ...wf.definition.nodes }
      delete nodes[nodeId]
      return { ...wf, definition: { ...wf.definition, nodes } }
    })
    setPositions(p => { const n = { ...p }; delete n[nodeId]; return n })
    if (selected === nodeId) setSelected(null)
    setDirty(true)
  }

  function moveNode(nodeId, x, y) {
    setPositions(p => ({ ...p, [nodeId]: { x, y } }))
  }

  function updateIntent(patch) {
    setWorkflow(wf => ({ ...wf, ...patch }))
    setDirty(true)
  }

  async function save() {
    if (!workflow || !dirty) return
    setSaving(true); setError(null)
    try {
      const body = {
        name:              workflow.name,
        description:       workflow.description,
        intent_definition: workflow.intent_definition,
        few_shot_examples: workflow.few_shot_examples || [],
        intent_threshold:  workflow.intent_threshold || 0.72,
        definition:        workflow.definition,
        is_active:         workflow.is_active !== false,
      }
      const url    = workflow.id
        ? `${API}/api/workflows/${workflow.id}`
        : `${API}/api/workflows`
      const method = workflow.id ? 'PUT' : 'POST'
      const res    = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const saved = await res.json()
      setWorkflow(saved)
      setDirty(false)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return {
    workflow, positions, selected, dirty, saving, error,
    loadWorkflow, addNode, updateNode, deleteNode, moveNode, updateIntent,
    setSelected, save,
  }
}
