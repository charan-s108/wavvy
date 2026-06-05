export default function TopBar({ callActive, callId }) {
  return (
    <div
      className="flex items-center justify-between px-6 h-14 flex-shrink-0"
      style={{ background: '#10131c', borderBottom: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center gap-3">
        <span className="t-body-18 text-w-text font-medium tracking-wide">Wavvy</span>
        <span className="t-caps text-w-hint">Agent Desktop</span>
      </div>

      <div className="flex items-center gap-3">
        {callActive ? (
          <div className="flex items-center gap-2">
            <div
              className="w-2 h-2 rounded-full bg-w-green"
              style={{ animation: 'callPulse 2s infinite' }}
            />
            <span className="t-body-14 text-w-muted">Live Call</span>
            {callId && (
              <span className="t-caps text-w-hint">{callId.slice(0, 8)}</span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-w-hint" />
            <span className="t-body-14 text-w-hint">Waiting for calls</span>
          </div>
        )}
      </div>
    </div>
  )
}
