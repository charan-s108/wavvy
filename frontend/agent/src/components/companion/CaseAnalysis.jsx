/**
 * CaseAnalysis — companion panel section showing:
 *   What Happened · Known Facts · Open Questions
 * Updates live as companion sends new_open_questions / resolved_questions.
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { CheckCircle2, HelpCircle, ChevronDown } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function CaseAnalysis({
  whatHappened,
  knownFacts = [],
  openQuestions = [],
}) {
  const [open, setOpen] = useState(true)

  if (!whatHappened && !knownFacts.length && !openQuestions.length) return null

  return (
    <div className="rounded-[14px] overflow-hidden"
      style={{ border: `1px solid ${Wa(0.07)}` }}>

      {/* Header */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        style={{ background: Wa(0.025) }}
      >
        <span className="t-caps text-[11px] text-white/55">Case Analysis</span>
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
            <div className="px-4 pb-4 pt-2 space-y-4">

              {/* What happened */}
              {whatHappened && (
                <div className="space-y-1.5">
                  <span className="t-caps text-[10px] text-white/40 block">What Happened</span>
                  <p className="text-[12px] leading-relaxed" style={{ color: Wa(0.75) }}>
                    {whatHappened}
                  </p>
                </div>
              )}

              {/* Known facts */}
              {knownFacts.length > 0 && (
                <div className="space-y-1.5">
                  <span className="t-caps text-[10px] text-white/40 block">What&apos;s Known</span>
                  <div className="space-y-1.5">
                    {knownFacts.map((f, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <CheckCircle2 size={11} style={{ color: '#1D9E75', flexShrink: 0, marginTop: 2 }} />
                        <div className="min-w-0">
                          <span className="text-[12px]" style={{ color: Wa(0.78) }}>{f.fact}</span>
                          {f.source && (
                            <span className="text-[10px] ml-1.5" style={{ color: Wa(0.35) }}>
                              · {f.source}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Open questions */}
              {openQuestions.length > 0 && (
                <div className="space-y-1.5">
                  <span className="t-caps text-[10px] text-white/40 block">Open Questions</span>
                  <div className="space-y-2">
                    {openQuestions.map((q, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <HelpCircle size={11} style={{ color: Y, flexShrink: 0, marginTop: 2 }} />
                        <div className="min-w-0">
                          <p className="text-[12px]" style={{ color: Wa(0.75) }}>
                            {typeof q === 'string' ? q : q.question}
                          </p>
                          {q.why && (
                            <p className="text-[10px] mt-0.5 italic" style={{ color: Wa(0.42) }}>
                              {q.why}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
