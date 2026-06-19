import { useEffect } from 'react'
import { X } from 'lucide-react'

const Wa = (a) => `rgba(255,255,255,${a})`

export default function Drawer({ open, onClose, title, subtitle, children, width = 500 }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.55)',
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'opacity 0.22s ease',
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 50,
          width,
          background: '#0d0f17',
          borderLeft: `1px solid ${Wa(0.08)}`,
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 0.26s cubic-bezier(0.4,0,0.2,1)',
          display: 'flex', flexDirection: 'column',
          overflowY: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: `1px solid ${Wa(0.07)}`,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <p style={{ fontSize: 15, fontWeight: 500, color: '#fff', lineHeight: 1.3, marginBottom: 2 }}>
              {title}
            </p>
            {subtitle && (
              <p style={{ fontSize: 11, color: Wa(0.40), letterSpacing: '0.4px' }}>
                {subtitle}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              flexShrink: 0,
              width: 30, height: 30,
              borderRadius: 8,
              background: Wa(0.04),
              border: `1px solid ${Wa(0.08)}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = Wa(0.09)}
            onMouseLeave={e => e.currentTarget.style.background = Wa(0.04)}
          >
            <X size={14} color={Wa(0.55)} />
          </button>
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {children}
        </div>
      </div>
    </>
  )
}
