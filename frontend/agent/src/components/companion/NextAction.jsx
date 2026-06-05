import { ArrowRight } from 'lucide-react'

export default function NextAction({ nextAction, customerMood }) {
  if (!nextAction) return null

  const moodColor = {
    calm:       'rgba(255,255,255,0.4)',
    satisfied:  '#f4f73d',
    frustrated: 'rgba(255,255,255,0.8)',
    angry:      '#ffffff',
  }[customerMood] || 'rgba(255,255,255,0.3)'

  return (
    <div
      className="rounded-xl p-3"
      style={{ background: '#10131c', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      {customerMood && (
        <div className="flex items-center gap-1.5 mb-2">
          <span className="t-caps text-w-hint">Mood</span>
          <span className="t-caps" style={{ color: moodColor }}>{customerMood}</span>
        </div>
      )}
      <div className="flex items-start gap-2">
        <ArrowRight size={14} color="#f4f73d" className="flex-shrink-0 mt-0.5" />
        <p className="t-body-12 text-w-text">{nextAction}</p>
      </div>
    </div>
  )
}
