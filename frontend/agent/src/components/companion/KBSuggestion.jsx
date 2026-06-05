import { BookOpen } from 'lucide-react'

export default function KBSuggestion({ kbSuggestion }) {
  if (!kbSuggestion) return null

  return (
    <div
      className="rounded-xl p-3"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <BookOpen size={12} color="#f4f73d" />
        <span className="t-caps" style={{ color: '#f4f73d' }}>KB Match</span>
        {kbSuggestion.source && (
          <span className="t-caps text-w-hint ml-auto">{kbSuggestion.source}</span>
        )}
      </div>
      <p className="t-body-12 text-w-muted">{kbSuggestion.content}</p>
    </div>
  )
}
