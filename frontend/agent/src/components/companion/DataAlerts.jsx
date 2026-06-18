/**
 * DataAlerts — data inconsistency warnings for the companion panel.
 * These are always top-priority, persist until dismissed.
 * NOT suggestions — WARNINGS.
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { AlertTriangle, AlertCircle, X } from 'lucide-react'

const SEVERITY_CONFIG = {
  HIGH:   { icon: AlertTriangle, color: '#fc535b', bg: 'rgba(252,83,91,0.06)', border: 'rgba(252,83,91,0.28)' },
  MEDIUM: { icon: AlertCircle,   color: '#fabc2d', bg: 'rgba(250,188,45,0.06)', border: 'rgba(250,188,45,0.22)' },
  LOW:    { icon: AlertCircle,   color: 'rgba(255,255,255,0.5)', bg: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.1)' },
}

export default function DataAlerts({ inconsistencies = [] }) {
  const [dismissed, setDismissed] = useState(new Set())

  const visible = inconsistencies.filter(inc => !dismissed.has(inc.type))
  if (!visible.length) return null

  return (
    <div className="space-y-2.5">
      <AnimatePresence>
        {visible.map((inc) => {
          const cfg  = SEVERITY_CONFIG[inc.severity] || SEVERITY_CONFIG.LOW
          const Icon = cfg.icon
          return (
            <motion.div
              key={inc.type}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <div className="rounded-[13px] p-3.5 space-y-1.5"
                style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Icon size={13} style={{ color: cfg.color, flexShrink: 0 }} />
                    <span className="text-[12px] font-semibold leading-snug" style={{ color: cfg.color }}>
                      {inc.headline}
                    </span>
                  </div>
                  {inc.severity !== 'HIGH' && (
                    <button
                      onClick={() => setDismissed(prev => new Set([...prev, inc.type]))}
                      className="shrink-0 transition-opacity hover:opacity-100 opacity-50"
                      style={{ color: cfg.color }}
                    >
                      <X size={11} />
                    </button>
                  )}
                </div>
                <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255,255,255,0.68)' }}>
                  {inc.detail}
                </p>
              </div>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
