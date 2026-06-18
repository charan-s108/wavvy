/**
 * LiveDocumentation — sticky footer showing ACW building in real time.
 * Human can see notes accumulating — no end-of-call anxiety.
 * Collapses to a pill; expands on click.
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { FileText, ChevronUp } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function LiveDocumentation({ liveDoc }) {
  const [open, setOpen] = useState(false)

  if (!liveDoc?.summary) return null

  return (
    <div className="shrink-0" style={{ borderTop: `1px solid ${Wa(0.06)}` }}>
      {/* Collapsed pill */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors"
        style={{ background: open ? Ya(0.04) : 'transparent' }}
      >
        <span className="flex items-center gap-2 t-caps text-[10px]" style={{ color: open ? Y : Wa(0.45) }}>
          <FileText size={9} />
          Live Notes
          <span className="text-[10px] font-mono" style={{ color: Wa(0.3) }}>
            {liveDoc.action_items?.length > 0 ? `· ${liveDoc.action_items.length} action${liveDoc.action_items.length > 1 ? 's' : ''}` : '· building…'}
          </span>
        </span>
        <ChevronUp size={11} className={`transition-transform ${open ? '' : 'rotate-180'}`}
          style={{ color: Wa(0.3) }} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 space-y-3" style={{ background: Ya(0.02) }}>
              <p className="text-[12px] leading-relaxed pt-2" style={{ color: Wa(0.72) }}>
                {liveDoc.summary}
              </p>

              {(liveDoc.action_items || []).length > 0 && (
                <div className="space-y-1">
                  <span className="t-caps text-[10px] text-white/38 block">Action Items</span>
                  {liveDoc.action_items.map((item, i) => (
                    <p key={i} className="text-[11px] flex items-start gap-1.5" style={{ color: Wa(0.65) }}>
                      <span style={{ color: Y, flexShrink: 0 }}>·</span> {item}
                    </p>
                  ))}
                </div>
              )}

              {liveDoc.crm_fields?.notes && (
                <div className="space-y-1">
                  <span className="t-caps text-[10px] text-white/38 block">CRM Note</span>
                  <p className="text-[11px]" style={{ color: Wa(0.55) }}>
                    {liveDoc.crm_fields.notes}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
