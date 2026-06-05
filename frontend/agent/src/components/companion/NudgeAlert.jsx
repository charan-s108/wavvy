import { Lightbulb } from 'lucide-react'

export default function NudgeAlert({ nudge }) {
  if (!nudge) return null

  return (
    <div
      className="rounded-xl p-3 flex items-start gap-2"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <Lightbulb size={14} color="rgba(255,255,255,0.4)" className="flex-shrink-0 mt-0.5" />
      <p className="t-body-12 text-w-muted">{nudge}</p>
    </div>
  )
}
