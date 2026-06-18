import { useRef } from 'react'

const NODE_COLORS = {
  collect: '#1378d1',
  action:  '#9543f6',
  branch:  '#fabc2d',
  inform:  '#1D9E75',
  end:     '#fc535b',
}

export default function WorkflowNodeCard({ node, position, selected, onSelect, onMove }) {
  const dragStart = useRef(null)

  function handleMouseDown(e) {
    if (e.target.closest('[data-port]')) return  // ignore port clicks
    e.stopPropagation()
    dragStart.current = { mx: e.clientX, my: e.clientY, ox: position.x, oy: position.y }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup',   onMouseUp)
  }

  function onMouseMove(e) {
    if (!dragStart.current) return
    const dx = e.clientX - dragStart.current.mx
    const dy = e.clientY - dragStart.current.my
    onMove(node.id, dragStart.current.ox + dx, dragStart.current.oy + dy)
  }

  function onMouseUp() {
    dragStart.current = null
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup',   onMouseUp)
  }

  const color = NODE_COLORS[node.node_type] || '#667085'
  const slots  = Object.keys(node.variables || {})

  return (
    <div
      onMouseDown={handleMouseDown}
      onClick={() => onSelect(node.id)}
      style={{
        position: 'absolute',
        left: position.x, top: position.y,
        width: 200, borderRadius: 10, overflow: 'visible',
        background: '#1b1d2a',
        border: `1.5px solid ${selected ? color : 'rgba(255,255,255,0.1)'}`,
        boxShadow: selected ? `0 0 0 2px ${color}44` : 'none',
        cursor: 'grab', userSelect: 'none', zIndex: selected ? 10 : 5,
      }}
    >
      {/* Header */}
      <div style={{
        background: color, borderRadius: '8px 8px 0 0',
        padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span style={{ color: '#fff', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8 }}>
          {node.node_type}
        </span>
        <span style={{ flex: 1, color: '#fff', fontSize: 12, fontWeight: 500,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {node.name}
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: '8px 10px' }}>
        {node.directive && (
          <div style={{ color: '#b2b2b4', fontSize: 11, marginBottom: 6,
            overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical' }}>
            {node.directive}
          </div>
        )}
        {slots.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {slots.map(s => (
              <span key={s} style={{
                padding: '1px 6px', borderRadius: 4,
                background: 'rgba(255,255,255,0.06)',
                color: '#b2b2b4', fontSize: 10,
              }}>{s}</span>
            ))}
          </div>
        )}
      </div>

      {/* Output port */}
      <div data-port="out" data-node={node.id} style={{
        position: 'absolute', right: -7, top: '50%', transform: 'translateY(-50%)',
        width: 14, height: 14, borderRadius: '50%',
        background: color, border: '2px solid #14131d', cursor: 'crosshair',
      }} />
      {/* Input port */}
      <div data-port="in" data-node={node.id} style={{
        position: 'absolute', left: -7, top: '50%', transform: 'translateY(-50%)',
        width: 14, height: 14, borderRadius: '50%',
        background: '#14131d', border: `2px solid ${color}`, cursor: 'default',
      }} />
    </div>
  )
}
