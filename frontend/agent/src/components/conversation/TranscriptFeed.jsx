import { useEffect, useRef } from 'react'

const SPEAKER_STYLES = {
  customer:  { label: 'Customer', color: 'rgba(255,255,255,0.7)', bg: 'rgba(255,255,255,0.04)' },
  agent:     { label: 'Agent',    color: '#f4f73d',               bg: 'rgba(244,247,61,0.06)' },
  voice_ai:  { label: 'Fin',      color: '#f4f73d',               bg: 'rgba(244,247,61,0.04)' },
  system:    { label: 'System',   color: 'rgba(255,255,255,0.25)', bg: 'transparent' },
}

export default function TranscriptFeed({ lines }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  if (!lines?.length) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="t-body-14 text-w-hint">Transcript will appear here...</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2">
      {lines.map((line, i) => {
        const style = SPEAKER_STYLES[line.speaker] || SPEAKER_STYLES.system
        return (
          <div
            key={i}
            className="rounded-lg px-3 py-2"
            style={{ background: style.bg }}
          >
            <p className="t-caps mb-0.5" style={{ color: style.color }}>{style.label}</p>
            <p className="t-body-14 text-w-muted">{line.text}</p>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
