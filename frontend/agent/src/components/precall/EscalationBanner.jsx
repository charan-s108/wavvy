import { AlertTriangle } from 'lucide-react'

const REASON_LABELS = {
  customer_request: 'Prospect Requested Wavvy Team',
  low_sentiment:    'Low Sentiment — Prospect Frustrated',
  tool_failure:     'Tool Error — Escalated for Recovery',
  unknown_threshold:'Multiple Unrecognized Requests',
  enterprise_pricing: 'Enterprise Pricing Inquiry',
}

export default function EscalationBanner({ handoffBundle }) {
  if (!handoffBundle) return null

  const reason = handoffBundle.reason || 'escalated'
  const label = REASON_LABELS[reason] || reason

  return (
    <div
      className="mx-4 mt-4 rounded-xl p-3 flex items-start gap-3"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)' }}
    >
      <AlertTriangle size={16} color="rgba(255,255,255,0.6)" className="flex-shrink-0 mt-0.5" />
      <div>
        <p className="t-caps" style={{ color: 'rgba(255,255,255,0.7)' }}>Escalated from Voice AI</p>
        <p className="t-body-12 text-w-muted mt-1">{label}</p>
        {handoffBundle.sentiment_status && (
          <p className="t-caps text-w-hint mt-1">
            Sentiment: {handoffBundle.sentiment_status}
          </p>
        )}
      </div>
    </div>
  )
}
