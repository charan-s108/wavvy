import { useState, useEffect, useRef } from 'react'
import { PhoneOff, Hash, Mic, MicOff, Headphones } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

const DTMF_KEYS = ['1','2','3','4','5','6','7','8','9','*','0','⌫']
const WAVE_HEIGHTS = [10, 20, 34, 48, 34, 20, 10]

function formatTime(secs) {
  const m = Math.floor(secs / 60).toString().padStart(2, '0')
  const s = (secs % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function WaveBars({ active, humanConnected = false }) {
  const barColor  = humanConnected ? 'var(--app-success)' : 'var(--yellow-1)'
  const glowColor = humanConnected ? 'rgba(29,158,117,0.18)' : 'rgba(244,247,61,0.13)'
  return (
    <div className="relative flex items-center justify-center" style={{ height: 72 }}>
      {active && (
        <div
          className="absolute"
          style={{
            bottom: 4,
            width: 120, height: 20,
            background: glowColor,
            filter: 'blur(22px)',
            borderRadius: '50%',
          }}
        />
      )}
      <div className="flex items-center justify-center gap-[8px]">
        {WAVE_HEIGHTS.map((h, i) => {
          const peak = h / 48
          return (
            <motion.div
              key={i}
              animate={active ? {
                scaleY: [0.08, peak * 0.55 + 0.12, peak, peak * 0.38, 0.08],
              } : { scaleY: 0.06 }}
              transition={active ? {
                duration: 0.6 + i * 0.055,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: i * 0.06,
              } : { duration: 0.4, ease: 'easeOut' }}
              style={{
                width: 3.5,
                height: h,
                borderRadius: 99,
                background: barColor,
                opacity: 0.3 + peak * 0.7,
                transformOrigin: 'center',
              }}
            />
          )
        })}
      </div>
    </div>
  )
}

export default function CallScreen({
  transcript,
  agentBuffer,
  micOn,
  speakerOn,
  onToggleMic,
  onToggleSpeaker,
  onEndCall,
  onKeypadSubmit,   // called once when user clicks Done (not on every keypress)
  onRequestHuman,
  escalating     = false,
  escalated      = false,
  humanConnected = false,
  otpCode        = null,
}) {
  const [keypadOpen,        setKeypadOpen]        = useState(false)
  const [keypadBuffer,      setKeypadBuffer]      = useState('')
  const [elapsed,           setElapsed]           = useState(0)
  const [showJoinedBanner,  setShowJoinedBanner]  = useState(false)
  const prevHumanConnected = useRef(false)

  useEffect(() => {
    const id = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Show a brief "Specialist connected" banner when humanConnected first becomes true
  useEffect(() => {
    if (humanConnected && !prevHumanConnected.current) {
      setShowJoinedBanner(true)
      const t = setTimeout(() => setShowJoinedBanner(false), 3000)
      prevHumanConnected.current = true
      return () => clearTimeout(t)
    }
  }, [humanConnected])

  // Auto-open keypad when OTP arrives
  useEffect(() => {
    if (otpCode) setKeypadOpen(true)
  }, [otpCode])

  const isAiSpeaking   = agentBuffer.length > 0
  const lastSpeech     = [...transcript].reverse().find(t => t.speaker !== 'system')
  const captionSpeaker = isAiSpeaking ? 'voice_ai' : (lastSpeech?.speaker ?? null)
  const captionText    = isAiSpeaking ? agentBuffer : (lastSpeech?.text ?? null)
  const waveActive     = isAiSpeaking || micOn

  const pressKey = (key) => {
    if (key === '⌫') {
      setKeypadBuffer(prev => prev.slice(0, -1))
    } else if (key !== '*' && keypadBuffer.length < 15) {
      setKeypadBuffer(prev => prev + key)
    }
  }

  const handleDone = () => {
    if (keypadBuffer) onKeypadSubmit?.(keypadBuffer)
    setKeypadOpen(false)
    setKeypadBuffer('')
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">

      {/* ── Main content area ──────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">

          {keypadOpen ? (
            <motion.div
              key="keypad"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col items-center justify-center h-full px-5 py-4 gap-3"
            >
              <p className="t-caps" style={{ color: 'rgba(255,255,255,0.28)' }}>
                {otpCode ? 'Enter OTP or Phone' : 'Enter Number'}
              </p>

              {/* Display */}
              <div
                style={{
                  fontFamily: 'monospace',
                  fontSize: '22px',
                  fontWeight: 300,
                  letterSpacing: '0.18em',
                  color: '#fff',
                  minHeight: 30,
                  textAlign: 'center',
                }}
              >
                {keypadBuffer
                  ? keypadBuffer.split('').join(' ')
                  : <span style={{ color: 'rgba(255,255,255,0.16)', fontSize: '17px' }}>· · · · · ·</span>
                }
              </div>

              {/* Keypad grid */}
              <div
                className="grid gap-2 w-full"
                style={{ gridTemplateColumns: 'repeat(3, 1fr)', maxWidth: 198 }}
              >
                {DTMF_KEYS.map(key => {
                  const isBack = key === '⌫'
                  const isStar = key === '*'
                  return (
                    <motion.button
                      key={key}
                      whileTap={{ scale: 0.80 }}
                      onClick={() => pressKey(key)}
                      className="flex items-center justify-center select-none rounded-xl"
                      style={{
                        height: 40,
                        background: isBack ? 'rgba(252,83,91,0.07)' : 'rgba(255,255,255,0.04)',
                        border: isBack ? '1px solid rgba(252,83,91,0.16)' : '1px solid rgba(255,255,255,0.07)',
                        fontSize: isBack ? '12px' : isStar ? '19px' : '15px',
                        fontWeight: 400,
                        color: isBack ? 'var(--tomato)' : isStar ? 'rgba(255,255,255,0.22)' : '#fff',
                        cursor: 'pointer',
                      }}
                    >
                      {key}
                    </motion.button>
                  )
                })}
              </div>

              {/* Done — sends the buffer as a single message */}
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={handleDone}
                className="rounded-full t-body-14"
                style={{
                  width: '100%', maxWidth: 198, padding: '9px 0',
                  background: keypadBuffer ? 'rgba(244,247,61,0.1)' : 'rgba(255,255,255,0.05)',
                  border: keypadBuffer ? '1px solid rgba(244,247,61,0.22)' : '1px solid rgba(255,255,255,0.08)',
                  color: keypadBuffer ? 'var(--yellow-1)' : 'rgba(255,255,255,0.42)',
                  cursor: 'pointer',
                }}
              >
                {keypadBuffer ? 'Send' : 'Cancel'}
              </motion.button>
            </motion.div>

          ) : (

            <motion.div
              key="wave"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col items-center justify-center h-full gap-4 px-6 py-6"
            >
              {/* Caption */}
              <div className="w-full flex flex-col items-center text-center" style={{ minHeight: 72 }}>
                <AnimatePresence mode="wait">
                  {captionText ? (
                    <motion.div
                      key={captionSpeaker}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.22 }}
                      className="flex flex-col items-center gap-2"
                    >
                      <span
                        className="t-caps"
                        style={{ color: captionSpeaker === 'voice_ai' ? 'var(--yellow-1)' : 'rgba(255,255,255,0.42)' }}
                      >
                        {captionSpeaker === 'voice_ai' ? 'Fin' : captionSpeaker === 'agent' ? 'Specialist' : 'You'}
                      </span>
                      <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.88)', maxWidth: 300, lineHeight: 1.65 }}>
                        {captionText}
                        {isAiSpeaking && (
                          <motion.span
                            animate={{ opacity: [1, 0] }}
                            transition={{ duration: 0.5, repeat: Infinity }}
                            style={{ color: 'var(--yellow-1)', marginLeft: 2 }}
                          >▍</motion.span>
                        )}
                      </p>
                    </motion.div>
                  ) : (
                    <motion.p
                      key="idle"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="t-caps"
                      style={{ color: humanConnected ? 'rgba(29,158,117,0.55)' : 'rgba(255,255,255,0.16)' }}
                    >
                      {humanConnected ? 'Specialist on the line' : 'Speak to start'}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              <WaveBars active={waveActive} humanConnected={humanConnected} />

              <p style={{ fontFamily: 'monospace', fontSize: '11px', letterSpacing: '0.18em', color: 'rgba(255,255,255,0.18)' }}>
                {formatTime(elapsed)}
              </p>
            </motion.div>
          )}

        </AnimatePresence>
      </div>

      {/* ── Specialist joined banner (auto-dismisses after 3s) ── */}
      <AnimatePresence>
        {showJoinedBanner && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22 }}
            className="flex items-center justify-center gap-2 mx-4 mb-1 px-3 py-2 rounded-xl flex-shrink-0"
            style={{
              background: 'rgba(29,158,117,0.08)',
              border: '1px solid rgba(29,158,117,0.22)',
            }}
          >
            <span className="block w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: 'var(--app-success)' }} />
            <span className="t-caps" style={{ color: 'var(--app-success)', fontSize: '9px' }}>
              Specialist connected — you can speak now
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Controls bar ────────────────────────────────────────── */}
      <div
        className="flex items-center gap-2 px-4 py-4 flex-shrink-0"
        style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
      >
        {/* Mic */}
        <motion.button
          whileTap={{ scale: 0.88 }}
          onClick={onToggleMic}
          title={micOn ? 'Mute' : 'Unmute'}
          className="flex flex-col items-center justify-center gap-0.5 flex-shrink-0 rounded-full"
          style={{
            width: 46, height: 46,
            background: micOn ? 'rgba(244,247,61,0.07)' : 'rgba(252,83,91,0.09)',
            border: micOn ? '1px solid rgba(244,247,61,0.18)' : '1px solid rgba(252,83,91,0.2)',
          }}
        >
          {micOn
            ? <Mic size={14} color="var(--yellow-1)" />
            : <MicOff size={14} color="var(--tomato)" />
          }
          <span className="t-caps" style={{ fontSize: '7px', color: micOn ? 'rgba(244,247,61,0.5)' : 'rgba(252,83,91,0.55)' }}>
            {micOn ? 'LIVE' : 'OFF'}
          </span>
        </motion.button>

        {/* Keypad */}
        <motion.button
          whileTap={{ scale: 0.88 }}
          onClick={() => { setKeypadOpen(p => !p); if (keypadOpen) setKeypadBuffer('') }}
          title="Keypad"
          className="flex flex-col items-center justify-center gap-0.5 flex-shrink-0 rounded-full"
          style={{
            width: 46, height: 46,
            background: keypadOpen ? 'rgba(244,247,61,0.07)' : 'rgba(255,255,255,0.04)',
            border: keypadOpen ? '1px solid rgba(244,247,61,0.18)' : '1px solid rgba(255,255,255,0.07)',
          }}
        >
          <Hash size={14} color={keypadOpen ? 'var(--yellow-1)' : 'rgba(255,255,255,0.35)'} />
          <span className="t-caps" style={{ fontSize: '7px', color: keypadOpen ? 'rgba(244,247,61,0.5)' : 'rgba(255,255,255,0.2)' }}>
            {otpCode ? 'OTP' : 'Input'}
          </span>
        </motion.button>

        {/* Talk to Human */}
        <motion.button
          whileTap={!escalated && !escalating && !humanConnected ? { scale: 0.96 } : {}}
          onClick={!escalated && !escalating && !humanConnected ? onRequestHuman : undefined}
          disabled={escalated || escalating || humanConnected}
          className="flex items-center justify-center gap-1.5 rounded-full flex-1 t-body-14"
          style={{
            height: 46,
            background: humanConnected || escalated ? 'rgba(29,158,117,0.08)' : 'rgba(255,255,255,0.04)',
            border: humanConnected || escalated ? '1px solid rgba(29,158,117,0.22)' : '1px solid rgba(255,255,255,0.08)',
            color: humanConnected || escalated ? 'var(--app-success)' : 'rgba(255,255,255,0.6)',
            cursor: escalated || escalating || humanConnected ? 'default' : 'pointer',
            opacity: escalating ? 0.5 : 1,
            whiteSpace: 'nowrap',
            transition: 'all 0.2s',
          }}
        >
          <Headphones size={13} />
          {humanConnected ? 'Connected' : escalated ? 'Requested' : escalating ? 'Connecting…' : 'Human'}
        </motion.button>

        {/* End Call */}
        <motion.button
          whileTap={{ scale: 0.88 }}
          onClick={onEndCall}
          className="flex items-center gap-1.5 rounded-full flex-shrink-0 t-body-14"
          style={{
            height: 46, padding: '0 18px',
            background: 'var(--tomato)',
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          <PhoneOff size={13} />
          End
        </motion.button>
      </div>
    </div>
  )
}
