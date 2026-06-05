export default function VoiceAIHistory({ voiceTranscript }) {
  if (!voiceTranscript?.length) return null

  return (
    <div className="mx-4 mt-3">
      <p className="t-caps text-w-hint mb-2">Voice AI Transcript (Pre-Escalation)</p>
      <div
        className="rounded-xl p-3 flex flex-col gap-2 max-h-40 overflow-y-auto"
        style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.06)' }}
      >
        {voiceTranscript.map((line, i) => (
          <div key={i} className="flex gap-2">
            <span
              className="t-caps flex-shrink-0 mt-0.5"
              style={{ color: line.speaker === 'voice_ai' ? '#f4f73d' : 'rgba(255,255,255,0.25)' }}
            >
              {line.speaker === 'voice_ai' ? 'AI' : 'CX'}
            </span>
            <p className="t-body-12 text-w-muted">{line.text}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
