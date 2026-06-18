/**
 * HandoffCard — fills Column 2 when callerState === 'incoming'.
 * Shows: escalation type + risk, what happened, known facts,
 * data inconsistency warnings, and open questions.
 * NO "proposed action" or AI verdict — human decides after reading.
 */
import { motion, AnimatePresence } from 'motion/react'
import { Phone, PhoneOff, ShieldCheck, AlertTriangle, HelpCircle, CheckCircle2 } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

const ESC_TYPE_LABELS = {
  emotion:   { label: 'Emotion',   color: '#fc535b', bg: 'rgba(252,83,91,0.1)', border: 'rgba(252,83,91,0.25)' },
  authority: { label: 'Authority', color: '#fabc2d', bg: 'rgba(250,188,45,0.1)', border: 'rgba(250,188,45,0.25)' },
  ambiguity: { label: 'Ambiguity', color: '#9543f6', bg: 'rgba(149,67,246,0.1)', border: 'rgba(149,67,246,0.25)' },
  novelty:   { label: 'Novelty',   color: Wa(0.6),   bg: Wa(0.05), border: Wa(0.15) },
}

const RISK_CONFIG = {
  HIGH:   { color: '#fc535b', bg: 'rgba(252,83,91,0.1)',  border: 'rgba(252,83,91,0.25)' },
  MEDIUM: { color: '#fabc2d', bg: 'rgba(250,188,45,0.1)', border: 'rgba(250,188,45,0.25)' },
  LOW:    { color: Wa(0.5),   bg: Wa(0.04),               border: Wa(0.12) },
}

function SkeletonLine({ width = '80%' }) {
  return (
    <div className="h-3 rounded-full animate-pulse" style={{ width, background: Wa(0.07) }} />
  )
}

export default function HandoffCard({
  customer,
  handoff,
  caseInvestigation,
  onAccept,
  onDecline,
}) {
  const esc   = caseInvestigation
  const etype = ESC_TYPE_LABELS[esc?.escalation_type] || ESC_TYPE_LABELS.novelty
  const risk  = RISK_CONFIG[esc?.risk] || RISK_CONFIG.LOW
  const investigating = !esc || esc.case_status !== 'investigation_complete'

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6 space-y-5">

        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="t-caps text-[11px]" style={{ color: Y }}>Incoming Call</span>
              {investigating && (
                <span className="text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1"
                  style={{ background: Ya(0.07), color: Y, border: `1px solid ${Ya(0.18)}` }}>
                  <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: Y }} />
                  Analysing case…
                </span>
              )}
            </div>
            <h3 className="text-base font-semibold text-white">
              {customer?.name || 'Customer'} is on the line
            </h3>
            {handoff?.reason && (
              <p className="text-[13px] mt-1 leading-relaxed" style={{ color: Wa(0.62) }}>
                {handoff.reason}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {esc?.escalation_type && (
              <span className="text-[11px] font-semibold px-2 py-1 rounded-full"
                style={{ background: etype.bg, color: etype.color, border: `1px solid ${etype.border}` }}>
                {etype.label}
              </span>
            )}
            {esc?.risk && (
              <span className="text-[11px] font-semibold px-2 py-1 rounded-full"
                style={{ background: risk.bg, color: risk.color, border: `1px solid ${risk.border}` }}>
                {esc.risk} RISK
              </span>
            )}
          </div>
        </div>

        {/* ── Data Inconsistency Alerts (highest priority) ── */}
        {(esc?.data_inconsistencies || []).map((inc, i) => (
          <motion.div key={i}
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="rounded-[14px] p-4 space-y-2"
            style={{ background: 'rgba(252,83,91,0.06)', border: '1px solid rgba(252,83,91,0.28)' }}>
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} style={{ color: '#fc535b', flexShrink: 0 }} />
              <span className="text-[13px] font-semibold" style={{ color: '#fc535b' }}>
                {inc.headline}
              </span>
            </div>
            <p className="text-[12px] leading-relaxed" style={{ color: Wa(0.72) }}>
              {inc.detail}
            </p>
          </motion.div>
        ))}

        {/* ── What Happened ── */}
        <div className="rounded-[14px] p-4 space-y-2.5"
          style={{ background: Wa(0.03), border: `1px solid ${Wa(0.07)}` }}>
          <span className="t-caps text-[11px] text-white/55 block">What Happened</span>
          {investigating ? (
            <div className="space-y-2">
              <SkeletonLine width="95%" />
              <SkeletonLine width="80%" />
              <SkeletonLine width="65%" />
            </div>
          ) : (
            <p className="text-[13px] leading-relaxed" style={{ color: Wa(0.82) }}>
              {esc.what_happened || 'Case analysis complete — see known facts below.'}
            </p>
          )}
        </div>

        {/* ── Already Confirmed ── */}
        {(esc?.known_facts || []).length > 0 && (
          <div className="space-y-2">
            <span className="t-caps text-[11px] text-white/50 block">Already Confirmed</span>
            <div className="space-y-1.5">
              {esc.known_facts.map((f, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <CheckCircle2 size={13} style={{ color: '#1D9E75', flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <span className="text-[13px]" style={{ color: Wa(0.82) }}>{f.fact}</span>
                    <span className="text-[11px] ml-1.5" style={{ color: Wa(0.38) }}>· {f.source}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Open Questions ── */}
        <AnimatePresence>
          {(esc?.open_questions || []).length > 0 && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="space-y-2">
              <span className="t-caps text-[11px] text-white/50 block">Open Questions</span>
              <div className="space-y-2">
                {esc.open_questions.map((q, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <HelpCircle size={13} style={{ color: Y, flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <p className="text-[13px]" style={{ color: Wa(0.78) }}>{q.question}</p>
                      {q.why && (
                        <p className="text-[11px] mt-0.5 italic" style={{ color: Wa(0.45) }}>{q.why}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Recommended Resolution ── */}
        {esc?.recommended_resolution && (
          <div className="rounded-[14px] p-4 space-y-2"
            style={{ background: Ya(0.03), border: `1px solid ${Ya(0.12)}` }}>
            <span className="t-caps text-[11px] flex items-center gap-1.5" style={{ color: Y }}>
              <ShieldCheck size={9} /> Recommended Approach
            </span>
            <p className="text-[13px] leading-relaxed" style={{ color: Wa(0.78) }}>
              {esc.recommended_resolution}
            </p>
          </div>
        )}

      </div>

      {/* ── Action Buttons (sticky footer) ── */}
      <div className="shrink-0 px-6 py-4 flex items-center gap-3"
        style={{ borderTop: `1px solid ${Wa(0.06)}`, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(12px)' }}>
        <button
          onClick={onDecline}
          className="flex-1 flex items-center justify-center gap-2 py-3 rounded-full text-[13px] font-medium transition-all"
          style={{ background: Wa(0.04), border: `1px solid ${Wa(0.12)}`, color: Wa(0.6) }}
          onMouseEnter={e => { e.currentTarget.style.background = Wa(0.08); e.currentTarget.style.color = Wa(0.85) }}
          onMouseLeave={e => { e.currentTarget.style.background = Wa(0.04); e.currentTarget.style.color = Wa(0.6) }}
        >
          <PhoneOff size={13} /> Decline
        </button>
        <motion.button
          whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
          onClick={onAccept}
          className="flex-2 flex-1 flex items-center justify-center gap-2 py-3 rounded-full text-[13px] font-bold tracking-wider transition-all"
          style={{ background: Y, color: '#000', boxShadow: `0 0 24px ${Ya(0.2)}` }}
        >
          <Phone size={13} /> Answer Call
        </motion.button>
      </div>
    </div>
  )
}
