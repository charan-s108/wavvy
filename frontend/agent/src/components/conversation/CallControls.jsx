import { PhoneOff, Mic, MicOff } from 'lucide-react'

const Wa = (a) => `rgba(255,255,255,${a})`

export default function CallControls({ callActive, connected, micEnabled, onToggleMic, onEndCall }) {
  if (!callActive) return null

  return (
    <div className="flex items-center justify-between px-4 py-3 flex-shrink-0"
      style={{ borderTop: `1px solid ${Wa(0.06)}` }}>
      {connected ? (
        <button onClick={onToggleMic}
          className="flex items-center gap-2 px-3 py-2 rounded-lg t-body-14 transition-all"
          style={{
            background: Wa(0.04),
            color:      Wa(micEnabled ? 0.6 : 0.35),
            border:     `1px solid ${Wa(0.1)}`,
          }}
          onMouseEnter={e => { e.currentTarget.style.color = '#fff' }}
          onMouseLeave={e => { e.currentTarget.style.color = Wa(micEnabled ? 0.6 : 0.35) }}
        >
          {micEnabled ? <Mic size={14} /> : <MicOff size={14} />}
          {micEnabled ? 'Mute' : 'Unmute'}
        </button>
      ) : (
        <div />
      )}

      <button onClick={onEndCall}
        className="flex items-center gap-2 px-4 py-2 rounded-lg t-body-14 font-medium transition-all"
        style={{ background: Wa(0.05), color: Wa(0.6), border: `1px solid ${Wa(0.12)}` }}
        onMouseEnter={e => { e.currentTarget.style.background = Wa(0.1); e.currentTarget.style.color = '#fff' }}
        onMouseLeave={e => { e.currentTarget.style.background = Wa(0.05); e.currentTarget.style.color = Wa(0.6) }}
      >
        <PhoneOff size={14} />
        End Call
      </button>
    </div>
  )
}
