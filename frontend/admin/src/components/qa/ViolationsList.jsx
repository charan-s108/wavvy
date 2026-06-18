import { AlertTriangle, CheckCircle2 } from 'lucide-react'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function ViolationsList({ violations, strengths }) {
  const hasViolations = violations?.length > 0
  const hasStrengths  = strengths?.length  > 0

  if (!hasViolations && !hasStrengths) return null

  return (
    <div className="flex flex-col gap-5">
      {hasViolations && (
        <div>
          <p className="section-label text-[10px] mb-3">Violations</p>
          <div className="flex flex-col gap-2">
            {violations.map((v, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-xl px-4 py-3"
                style={{ background: Wa(0.03), border: `1px solid ${Wa(0.08)}` }}
              >
                <AlertTriangle size={13} color={Wa(0.42)} className="flex-shrink-0 mt-0.5" />
                <p className="text-[12px] text-white/62 leading-relaxed">{v}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasStrengths && (
        <div>
          <p className="section-label text-[10px] mb-3">Strengths</p>
          <div className="flex flex-col gap-2">
            {strengths.map((s, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-xl px-4 py-3"
                style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}
              >
                <CheckCircle2 size={13} color={Y} className="flex-shrink-0 mt-0.5" />
                <p className="text-[12px] text-white/68 leading-relaxed">{s}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
