import { Phone, PhoneCall, PhoneOff, Mic, MicOff } from 'lucide-react'
import CRMCard from '../crm/CRMCard.jsx'
import EscalationBanner from '../precall/EscalationBanner.jsx'
import VoiceAIHistory from '../precall/VoiceAIHistory.jsx'
import TranscriptFeed from '../conversation/TranscriptFeed.jsx'
import CallControls from '../conversation/CallControls.jsx'
import CompanionPanel from '../companion/CompanionPanel.jsx'
import ACWSummary from '../acw/ACWSummary.jsx'
import ACWSubmit from '../acw/ACWSubmit.jsx'

export default function AgentShell({
  callActive,
  customer,
  handoffBundle,
  voiceTranscript,
  transcript,
  companion,
  acw,
  connected,
  joining,
  micEnabled,
  onAcceptCall,
  onToggleMic,
  onEndCall,
  onAcwSubmit,
}) {
  const showAcw = !!acw

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* LEFT — CRM + Pre-call context (280px) */}
      <div
        className="w-[280px] flex-shrink-0 overflow-y-auto flex flex-col"
        style={{ borderRight: '1px solid rgba(255,255,255,0.08)' }}
      >
        {/* Escalation banner */}
        {handoffBundle && <EscalationBanner handoffBundle={handoffBundle} />}

        {/* Voice AI pre-call transcript */}
        {voiceTranscript?.length > 0 && (
          <VoiceAIHistory voiceTranscript={voiceTranscript} />
        )}

        {/* Lead CRM card — populated after escalation from Voice AI */}
        <CRMCard lead={handoffBundle?.lead || customer} />
      </div>

      {/* CENTER — Live transcript + controls (flex-1) */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* ACW overlay */}
        {showAcw ? (
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
            <div>
              <p className="t-h3 text-w-text mb-1">After Call Work</p>
              <p className="t-body-14 text-w-hint">Review the auto-generated summary and submit</p>
            </div>
            <ACWSummary acw={acw} />
            <ACWSubmit acw={acw} onSubmit={onAcwSubmit} />
          </div>
        ) : callActive ? (
          <>
            {/* Accept banner — shown until agent joins the room */}
            {!connected && (
              <AcceptBanner
                joining={joining}
                handoffBundle={handoffBundle}
                onAccept={onAcceptCall}
              />
            )}
            {/* Live transcript — visible once connected */}
            {connected && <TranscriptFeed lines={transcript} />}
            <CallControls
              callActive={callActive}
              connected={connected}
              micEnabled={micEnabled}
              onToggleMic={onToggleMic}
              onEndCall={onEndCall}
            />
          </>
        ) : (
          <WaitingState />
        )}
      </div>

      {/* RIGHT — Companion AI (300px) */}
      <div
        className="w-[300px] flex-shrink-0 flex flex-col overflow-hidden"
        style={{ borderLeft: '1px solid rgba(255,255,255,0.08)' }}
      >
        <CompanionPanel companion={companion} callActive={callActive} />
      </div>
    </div>
  )
}

function AcceptBanner({ joining, handoffBundle, onAccept }) {
  const name = handoffBundle?.lead?.name || 'Customer'
  const reason = handoffBundle?.reason || 'customer_request'

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
      {/* Pulsing ring */}
      <div
        className="w-20 h-20 rounded-full flex items-center justify-center"
        style={{
          background: 'rgba(244,247,61,0.07)',
          border: '2px solid rgba(244,247,61,0.3)',
          animation: 'incomingPulse 2s ease-in-out infinite',
        }}
      >
        <PhoneCall size={28} color="#f4f73d" />
      </div>

      <div className="text-center">
        <p className="t-body-18-500 text-w-text mb-1">Incoming call from {name}</p>
        <p className="t-body-14 text-w-hint capitalize">{reason.replace(/_/g, ' ')}</p>
      </div>

      <button
        onClick={onAccept}
        disabled={joining}
        className="flex items-center gap-2 px-6 py-3 rounded-xl t-body-16-400 font-medium transition-all"
        style={{
          background: joining ? 'rgba(244,247,61,0.5)' : '#f4f73d',
          color: '#ffffff',
          cursor: joining ? 'wait' : 'pointer',
          opacity: joining ? 0.7 : 1,
        }}
      >
        <PhoneCall size={16} />
        {joining ? 'Connecting…' : 'Accept Call'}
      </button>

      <p className="t-body-14 text-w-hint text-center">
        Accepting will connect your microphone to the customer's call.
      </p>
    </div>
  )
}

function WaitingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
      <div
        className="w-16 h-16 rounded-full flex items-center justify-center"
        style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.08)',
          animation: 'incomingPulse 3s ease-in-out infinite',
        }}
      >
        <Phone size={24} color="rgba(255,255,255,0.35)" />
      </div>
      <div className="text-center">
        <p className="t-body-18 text-w-text mb-1">Ready for calls</p>
        <p className="t-body-14 text-w-hint">Escalated calls from Voice AI will appear here</p>
      </div>
    </div>
  )
}
