/**
 * Timeline — collapsible chronological event strip.
 * Shows pre-call events (transactions, refunds) and in-call AI steps.
 * Built from case_investigation.timeline — no LLM needed.
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Clock, ChevronDown } from 'lucide-react'

const Y  = '#f4f73d'
const Wa = (a) => `rgba(255,255,255,${a})`

export default function Timeline({ events = [] }) {
  const [open, setOpen] = useState(false)

  if (!events.length) return null

  return (
    <div className="rounded-[14px] overflow-hidden"
      style={{ border: `1px solid ${Wa(0.07)}` }}>

      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        style={{ background: Wa(0.025) }}
      >
        <span className="t-caps text-[11px] text-white/55 flex items-center gap-1.5">
          <Clock size={9} /> Timeline
          <span className="text-[10px] font-mono text-white/35 ml-1">({events.length})</span>
        </span>
        <ChevronDown size={12} className={`text-white/40 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="px-4 pt-2 pb-4 space-y-0">
              {events.map((ev, i) => {
                const isLast = i === events.length - 1
                const isEscalation = ev.event?.toLowerCase().includes('escalat')
                return (
                  <div key={i} className="flex items-start gap-3 relative">
                    {/* Vertical line */}
                    {!isLast && (
                      <div className="absolute left-[5px] top-4 bottom-0 w-px"
                        style={{ background: Wa(0.07) }} />
                    )}
                    {/* Dot */}
                    <div
                      className="mt-1 w-2.5 h-2.5 rounded-full shrink-0 relative z-10"
                      style={{
                        background: isEscalation ? Y : isLast ? Wa(0.4) : Wa(0.18),
                        border: `1px solid ${isEscalation ? Y : Wa(0.25)}`,
                      }}
                    />
                    {/* Content */}
                    <div className="pb-3 min-w-0">
                      <p className="text-[12px] leading-snug" style={{ color: isEscalation ? Y : Wa(0.72) }}>
                        {ev.event}
                      </p>
                      <p className="text-[10px] font-mono mt-0.5" style={{ color: Wa(0.35) }}>
                        {ev.ts}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
