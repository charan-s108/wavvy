import WorkflowNodeCard from './WorkflowNodeCard'

const NODE_COLORS = {
  collect: '#1378d1',
  action:  '#9543f6',
  branch:  '#fabc2d',
  inform:  '#1D9E75',
  end:     '#fc535b',
}

function getPortCenter(nodeId, positions, side = 'out') {
  const pos = positions[nodeId] || { x: 0, y: 0 }
  const NODE_W = 200, NODE_H = 100  // approximate; SVG uses estimated centers
  return {
    x: side === 'out' ? pos.x + NODE_W : pos.x,
    y: pos.y + NODE_H / 2,
  }
}

function EdgeLines({ nodes, positions }) {
  const lines = []
  Object.values(nodes).forEach(node => {
    ;(node.edges || []).forEach((edge, i) => {
      const tid = edge.target_node_id
      if (!tid || tid === '__end__' || !positions[tid]) return
      const from = getPortCenter(node.id, positions, 'out')
      const to   = getPortCenter(tid,     positions, 'in')
      const color = NODE_COLORS[node.node_type] || '#667085'
      const mx = (from.x + to.x) / 2
      lines.push(
        <g key={`${node.id}-${tid}-${i}`}>
          <path
            d={`M${from.x},${from.y} C${mx},${from.y} ${mx},${to.y} ${to.x},${to.y}`}
            fill="none" stroke={color} strokeWidth={1.5} strokeOpacity={0.5}
          />
          {/* Edge label */}
          <text x={mx} y={(from.y + to.y) / 2 - 6}
            fill={color} fontSize={9} textAnchor="middle" opacity={0.7}>
            {edge.condition}
          </text>
        </g>
      )
    })
  })
  return <>{lines}</>
}

export default function WorkflowCanvas({ workflow, positions, selected, onSelect, onMove }) {
  if (!workflow) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#727781' }}>
      Select or create a workflow
    </div>
  )

  const nodes  = workflow.definition?.nodes || {}
  const maxX   = Object.values(positions).reduce((m, p) => Math.max(m, p.x), 0) + 300
  const maxY   = Object.values(positions).reduce((m, p) => Math.max(m, p.y), 0) + 200

  return (
    <div style={{ flex: 1, overflow: 'auto', position: 'relative', background: '#10131c' }}>
      {/* SVG edge layer — pointer-events: none so nodes stay clickable */}
      <svg style={{ position: 'absolute', top: 0, left: 0, width: maxX, height: maxY, pointerEvents: 'none' }}>
        <EdgeLines nodes={nodes} positions={positions} />
      </svg>

      {/* Node cards */}
      <div style={{ position: 'relative', width: maxX, height: maxY }}>
        {Object.values(nodes).map(node => (
          <WorkflowNodeCard
            key={node.id}
            node={node}
            position={positions[node.id] || { x: 40, y: 40 }}
            selected={selected === node.id}
            onSelect={onSelect}
            onMove={onMove}
          />
        ))}
      </div>
    </div>
  )
}
