import { FileText } from 'lucide-react'

const Y  = '#f4f73d'
const Wa = (a) => `rgba(255,255,255,${a})`

const RESOLUTION_COLORS = {
  resolved:   Y,
  escalated:  Wa(0.55),
  unresolved: Wa(0.35),
}

export default function ACWSummary({ acw }) {
  if (!acw) return null

  const resColor = RESOLUTION_COLORS[acw.resolution] || Wa(0.3)

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="t-caps mb-1.5" style={{ color: Wa(0.25) }}>Call Summary</p>
        <p className="t-body-14" style={{ color: Wa(0.55) }}>{acw.summary}</p>
      </div>

      <div className="flex items-center gap-2">
        <span className="t-caps" style={{ color: Wa(0.25) }}>Resolution</span>
        <span className="t-caps" style={{ color: resColor }}>{acw.resolution}</span>
      </div>

      {acw.action_items?.length > 0 && (
        <div>
          <p className="t-caps mb-1.5" style={{ color: Wa(0.25) }}>Action Items</p>
          <div className="flex flex-col gap-1">
            {acw.action_items.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="w-1 h-1 rounded-full mt-2 flex-shrink-0" style={{ background: Y }} />
                <p className="t-body-12" style={{ color: Wa(0.5) }}>{item}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {acw.coaching_note && (
        <div className="rounded-xl p-3"
          style={{ background: `rgba(244,247,61,0.04)`, border: `1px solid rgba(244,247,61,0.12)` }}>
          <p className="t-caps mb-1" style={{ color: Y }}>Coaching Note</p>
          <p className="t-body-12" style={{ color: Wa(0.45) }}>{acw.coaching_note}</p>
        </div>
      )}
    </div>
  )
}
