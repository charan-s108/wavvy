import { User, Phone, Mail, Building2, Tag, Clock } from 'lucide-react'

const Y  = '#f4f73d'
const Wa = (a) => `rgba(255,255,255,${a})`

// All intents map to yellow (primary accent) or white variants only
const INTENT_COLORS = {
  payment_failure:  Y,
  refund_inquiry:   Wa(0.55),
  kyc_verification: Wa(0.55),
  fraud_report:     '#ffffff',
  account_access:   Y,
  general_inquiry:  Wa(0.35),
  demo_request:     Y,
  human_agent:      Y,
  product_qa:       Wa(0.55),
}

const STATUS_COLORS = {
  new:            Wa(0.35),
  active:         Y,
  escalated:      Wa(0.6),
  resolved:       Y,
  pending:        Wa(0.45),
  demo_scheduled: Y,
  converted:      Y,
}

export default function CRMCard({ lead }) {
  if (!lead) {
    return (
      <div className="p-4">
        <p className="t-body-14 text-center mt-8" style={{ color: Wa(0.25) }}>Waiting for call...</p>
      </div>
    )
  }

  const intentColor = INTENT_COLORS[lead.intent] || Wa(0.3)
  const statusColor = STATUS_COLORS[lead.status]  || Wa(0.3)
  const intentLabel = (lead.intent || 'unknown').replace(/_/g, ' ')

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Identity */}
      <div className="rounded-xl p-4"
        style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}>
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: Wa(0.04), border: `1px solid ${Wa(0.08)}` }}>
              <User size={16} color={Wa(0.5)} />
            </div>
            <div>
              <p className="t-body-14 text-white font-medium">{lead.name || 'Anonymous Visitor'}</p>
              <span className="t-caps" style={{ color: intentColor }}>{intentLabel}</span>
            </div>
          </div>
          <span className="t-caps" style={{ color: statusColor }}>{lead.status || 'new'}</span>
        </div>

        <div className="flex flex-col gap-2">
          {lead.phone && (
            <div className="flex items-center gap-2">
              <Phone size={12} color={Wa(0.25)} />
              <span className="t-body-12" style={{ color: Wa(0.5) }}>{lead.phone}</span>
            </div>
          )}
          {lead.email && (
            <div className="flex items-center gap-2">
              <Mail size={12} color={Wa(0.25)} />
              <span className="t-body-12" style={{ color: Wa(0.5) }}>{lead.email}</span>
            </div>
          )}
          {lead.company && (
            <div className="flex items-center gap-2">
              <Building2 size={12} color={Wa(0.25)} />
              <span className="t-body-12" style={{ color: Wa(0.5) }}>{lead.company}</span>
            </div>
          )}
        </div>
      </div>

      {/* Case Context */}
      <div className="rounded-xl p-3"
        style={{ background: `rgba(244,247,61,0.04)`, border: `1px solid rgba(244,247,61,0.12)` }}>
        <div className="flex items-center gap-1.5 mb-2">
          <Tag size={11} color={Y} />
          <p className="t-caps" style={{ color: Y }}>Case Context</p>
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="t-caps" style={{ color: Wa(0.25) }}>Intent</span>
            <span className="t-body-12" style={{ color: intentColor }}>{intentLabel}</span>
          </div>
          {lead.interest_notes && (
            <p className="t-body-12 mt-1" style={{ color: Wa(0.45) }}>{lead.interest_notes}</p>
          )}
        </div>
      </div>

      {/* Appointment */}
      {lead.requested_time && (
        <div className="rounded-xl p-3"
          style={{ background: `rgba(244,247,61,0.04)`, border: `1px solid rgba(244,247,61,0.12)` }}>
          <div className="flex items-center gap-1.5 mb-1">
            <Clock size={11} color={Y} />
            <p className="t-caps" style={{ color: Y }}>Demo Scheduled</p>
          </div>
          <p className="t-body-12" style={{ color: Wa(0.5) }}>{lead.requested_time}</p>
        </div>
      )}
    </div>
  )
}
