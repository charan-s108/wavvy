import { useState, useCallback, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import CallScreen from './CallScreen.jsx'
import TransferScreen from './TransferScreen.jsx'
import FeedbackForm from './FeedbackForm.jsx'
import { useLiveKitVoice } from '../hooks/useLiveKitVoice.js'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || ''
const PHASE = { CONNECTING: 'connecting', CALLING: 'calling', TRANSFER: 'transfer', FEEDBACK: 'feedback' }

/* ── Status pill shown in header ─────────────────────────────── */
function StatusPill({ phase }) {
  const isLive     = phase === PHASE.CALLING
  const isConnect  = phase === PHASE.CONNECTING
  const isTransfer = phase === PHASE.TRANSFER

  const label = isLive ? 'Live' : isConnect ? 'Connecting' : isTransfer ? 'Transferring' : 'Ended'
  const dotBg = isLive
    ? 'var(--yellow-1)'
    : isConnect
      ? 'rgba(244,247,61,0.45)'
      : 'rgba(255,255,255,0.2)'

  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full"
      style={{
        background: isLive ? 'rgba(244,247,61,0.08)' : 'rgba(255,255,255,0.05)',
        border: `1px solid ${isLive ? 'rgba(244,247,61,0.2)' : 'rgba(255,255,255,0.08)'}`,
      }}
    >
      <span
        className="block rounded-full flex-shrink-0"
        style={{
          width: 6, height: 6,
          background: dotBg,
          boxShadow: isLive ? '0 0 0 0 rgba(244,247,61,0.4)' : 'none',
          animation: isLive ? 'callPulse 2s infinite' : 'none',
        }}
      />
      <span className="t-caps" style={{ color: isLive ? 'var(--yellow-1)' : 'rgba(255,255,255,0.38)', fontSize: '9px' }}>
        {label}
      </span>
    </div>
  )
}

export default function CallModal({ open, onClose, backendStatus }) {
  const [phase,       setPhase]       = useState(PHASE.CONNECTING)
  const [transcript,  setTranscript]  = useState([])
  const [micOn,       setMicOn]       = useState(true)
  const [speakerOn,   setSpeakerOn]   = useState(true)
  const [agentBuffer, setAgentBuffer] = useState('')
  const [callError,   setCallError]   = useState('')
  const [callId,      setCallId]      = useState(null)
  const [escalating,     setEscalating]     = useState(false)
  const [escalated,      setEscalated]      = useState(false)
  const [humanConnected, setHumanConnected] = useState(false)
  const [otpCode,        setOtpCode]        = useState(null)

  const addLine = useCallback((speaker, text) => {
    setTranscript(prev => [...prev, { speaker, text }])
  }, [])

  const onCallReady           = useCallback((msg) => {
    if (msg?.call_id) setCallId(msg.call_id)
    // Functional update: never regress from TRANSFER back to CALLING
    setPhase(prev => prev === PHASE.TRANSFER ? prev : PHASE.CALLING)
  }, [])
  const onEscalation          = useCallback((msg) => {
    setEscalated(true)
    setPhase(PHASE.TRANSFER)
    if (msg?.customer_esc_token && msg?.livekit_url) {
      connectToEscalationRoom(msg.customer_esc_token, msg.livekit_url)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const onEscalationCancelled = useCallback(() => {
    if (humanConnected) return  // human already joined — can't go back to AI
    setEscalated(false); setEscalating(false); setPhase(PHASE.CALLING)
  }, [humanConnected])
  const onHumanAgentJoined    = useCallback(() => {
    setHumanConnected(true)
    setPhase(PHASE.CALLING)
  }, [])
  const onCallEnded           = useCallback(() => setPhase(PHASE.FEEDBACK), [])
  const onAgentToken     = useCallback((tok) => setAgentBuffer(p => p + tok), [])
  const onAgentDone      = useCallback((full) => { addLine('voice_ai', full); setAgentBuffer('') }, [addLine])
  const onTranscript     = useCallback((speaker, text, isFinal) => { if (isFinal) addLine(speaker, text) }, [addLine])
  const onToolCall       = useCallback((tool, status) => { if (status === 'calling') addLine('system', `Calling ${tool}…`) }, [addLine])
  const onGuardrailBlock = useCallback((tool, reason) => { addLine('system', `⚠ ${tool} blocked: ${reason}`) }, [addLine])
  const onSentiment      = useCallback(() => {}, [])
  const onKbHit          = useCallback(() => {}, [])
  const onOtpSent        = useCallback((otp) => {
    setOtpCode(otp)
    addLine('system', `Demo OTP: ${otp}`)
  }, [addLine])
  const onOtpVerified    = useCallback(() => {
    setOtpCode(null)
  }, [])

  const { startCall, endCall, setMicEnabled, sendBrowserTranscript, getCallId, connectToEscalationRoom } = useLiveKitVoice({
    onCallReady, onTranscript, onAgentToken, onAgentDone,
    onEscalation, onEscalationCancelled, onHumanAgentJoined, onCallEnded,
    onToolCall, onGuardrailBlock, onSentiment, onKbHit, onOtpSent, onOtpVerified,
  })

  const revertToAI = useCallback(async () => {
    const cid = callId || getCallId()
    if (!cid) return
    try {
      await fetch(`${BACKEND}/api/calls/${cid}/cancel-escalation`, { method: 'POST' })
    } catch {}
    setEscalated(false)
    setEscalating(false)
    setPhase(PHASE.CALLING)
  }, [callId, getCallId])

  const requestHumanAgent = useCallback(async () => {
    const cid = callId || getCallId()
    if (!cid || escalating || escalated) return
    setEscalating(true)
    try {
      const resp = await fetch(`${BACKEND}/api/calls/${cid}/request-human`, { method: 'POST' })
      if (!resp.ok) throw new Error(`request-human failed: ${resp.status}`)
      setEscalated(true)
      setPhase(PHASE.TRANSFER)
    } catch (err) {
      console.error('Talk to Human failed:', err)
    } finally {
      setEscalating(false)
    }
  }, [callId, getCallId, escalating, escalated])

  const toggleMic = useCallback(async () => {
    const next = !micOn
    setMicOn(next)
    await setMicEnabled(next)
  }, [micOn, setMicEnabled])

  const handleKeypadDigit = useCallback((digits) => sendBrowserTranscript(digits), [sendBrowserTranscript])

  const handleEndCall = useCallback(() => {
    endCall()
    setPhase(PHASE.FEEDBACK)
  }, [endCall])

  const isCallActive = phase === PHASE.CONNECTING || phase === PHASE.CALLING || phase === PHASE.TRANSFER

  const handleClose = useCallback(() => {
    if (isCallActive) endCall()
    onClose()
  }, [isCallActive, endCall, onClose])

  // Track whether we've already started the call this open session
  const callStartedRef = useRef(false)

  useEffect(() => {
    if (!open) {
      callStartedRef.current = false
      return
    }
    setPhase(PHASE.CONNECTING)
    setTranscript([])
    setAgentBuffer('')
    setMicOn(true)
    setSpeakerOn(true)
    setCallError('')
    setCallId(null)
    setEscalating(false)
    setEscalated(false)
    setHumanConnected(false)
    setOtpCode(null)
    callStartedRef.current = false
  }, [open])

  // Auto-start the call once backend is online (handles cold-start gracefully)
  useEffect(() => {
    if (!open) return
    if (callStartedRef.current) return
    if (backendStatus !== 'online') return
    callStartedRef.current = true
    startCall(null).catch(err => setCallError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, backendStatus])

  return (
    <AnimatePresence>
      {open && (
        <>
        {/* ── Backdrop ─────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.82)', backdropFilter: 'blur(20px)' }}
          onClick={e => { if (e.target === e.currentTarget && !isCallActive) handleClose() }}
        >
          {/* ── Modal card ──────────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 34 }}
            className="w-full flex flex-col overflow-hidden"
            style={{
              maxWidth: 420,
              maxHeight: '86vh',
              background: '#080808',
              border: '1px solid var(--modal-border)',
              borderRadius: 24,
              boxShadow: '0 0 0 1px rgba(244,247,61,0.06) inset, 0 32px 80px rgba(0,0,0,0.9)',
            }}
          >
            {/* ── Header ──────────────────────────────────────── */}
            <div
              className="flex items-center justify-between px-5 py-3.5 flex-shrink-0"
              style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
            >
              <div className="flex items-center gap-2.5">
                <StatusPill phase={phase} />
                <span
                  className="t-body-14"
                  style={{ color: 'rgba(255,255,255,0.55)', fontWeight: 400 }}
                >
                  Fin
                </span>
                {otpCode && (
                  <span style={{ fontFamily: 'monospace', fontSize: '13px', fontWeight: 700, color: '#f4f73d', letterSpacing: '0.2em' }}>
                    {otpCode}
                  </span>
                )}
              </div>

              <button
                onClick={handleClose}
                className="flex items-center justify-center rounded-full transition-all"
                style={{
                  width: 30, height: 30,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  color: 'rgba(255,255,255,0.3)',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = '#fff' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; e.currentTarget.style.color = 'rgba(255,255,255,0.3)' }}
              >
                <X size={12} />
              </button>
            </div>

            {/* ── Error banner ────────────────────────────────── */}
            {callError && (
              <div
                className="px-5 py-2 flex-shrink-0 t-caps"
                style={{ background: 'rgba(252,83,91,0.1)', color: 'var(--tomato)', borderBottom: '1px solid rgba(252,83,91,0.15)' }}
              >
                ⚠ {callError}
              </div>
            )}


            {/* ── Phase content ───────────────────────────────── */}
            <div className="flex flex-col flex-1 overflow-hidden">

              {phase === PHASE.CONNECTING && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex-1 flex flex-col items-center justify-center gap-6 px-6 py-12"
                >
                  {/* Ripple rings */}
                  <div className="relative flex items-center justify-center" style={{ width: 96, height: 96 }}>
                    {[0, 1, 2].map(i => (
                      <motion.span
                        key={i}
                        className="absolute rounded-full"
                        style={{ border: `1px solid ${backendStatus === 'online' ? 'rgba(244,247,61,0.18)' : 'rgba(250,188,45,0.15)'}` }}
                        animate={{ width: [44, 44 + (i + 1) * 20], height: [44, 44 + (i + 1) * 20], opacity: [0.7, 0] }}
                        transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.45, ease: [0.2, 0, 0.8, 1] }}
                      />
                    ))}
                    <div
                      className="relative flex items-center justify-center rounded-full"
                      style={{
                        width: 44, height: 44,
                        background: backendStatus === 'online' ? 'rgba(244,247,61,0.07)' : 'rgba(250,188,45,0.07)',
                        border: `1px solid ${backendStatus === 'online' ? 'rgba(244,247,61,0.2)' : 'rgba(250,188,45,0.2)'}`,
                      }}
                    >
                      <div className="flex gap-1">
                        {[0, 1, 2].map(i => (
                          <motion.span
                            key={i}
                            className="block rounded-full"
                            style={{ width: 4, height: 4, background: backendStatus === 'online' ? 'var(--yellow-1)' : '#fabc2d' }}
                            animate={{ opacity: [0.2, 1, 0.2] }}
                            transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="text-center space-y-1.5">
                    {backendStatus !== 'online' ? (
                      <>
                        <p className="t-body-16" style={{ color: '#fabc2d', fontWeight: 500 }}>
                          Backend warming up…
                        </p>
                        <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.32)' }}>
                          HuggingFace Spaces can take ~30s to wake up.
                        </p>
                        <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.20)' }}>
                          Your call will start automatically once ready.
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="t-body-16" style={{ color: '#fff', fontWeight: 500 }}>
                          Connecting to Fin
                        </p>
                        <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.32)' }}>
                          Setting up your secure voice session…
                        </p>
                      </>
                    )}
                  </div>
                </motion.div>
              )}

              {phase === PHASE.CALLING && (
                <CallScreen
                  transcript={transcript}
                  agentBuffer={agentBuffer}
                  micOn={micOn}
                  speakerOn={speakerOn}
                  onToggleMic={toggleMic}
                  onToggleSpeaker={() => setSpeakerOn(p => !p)}
                  onEndCall={handleEndCall}
                  onKeypadSubmit={handleKeypadDigit}
                  onRequestHuman={requestHumanAgent}
                  escalating={escalating}
                  escalated={escalated}
                  humanConnected={humanConnected}
                  otpCode={otpCode}
                />
              )}

              {phase === PHASE.TRANSFER && (
                <TransferScreen
                  onEndCall={handleEndCall}
                  onRevertToAI={humanConnected ? null : revertToAI}
                  humanConnected={humanConnected}
                />
              )}

              {phase === PHASE.FEEDBACK && (
                <FeedbackForm callId={callId} onDone={onClose} />
              )}
            </div>
          </motion.div>
        </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
