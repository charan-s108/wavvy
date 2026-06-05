import { motion, AnimatePresence } from 'motion/react'
import { PhoneOff, Headphones, RotateCcw } from 'lucide-react'

export default function TransferScreen({ onEndCall, onRevertToAI, humanConnected = false }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-7 px-6 py-10">

      {/* Icon — pulsing yellow while connecting, steady green when connected */}
      <div className="relative flex items-center justify-center">
        <AnimatePresence mode="wait">
          {humanConnected ? (
            <motion.div
              key="connected"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', stiffness: 400, damping: 22 }}
              className="relative flex items-center justify-center rounded-full"
              style={{
                width: 52, height: 52,
                background: 'rgba(29,158,117,0.08)',
                border: '1.5px solid rgba(29,158,117,0.35)',
                boxShadow: '0 0 0 8px rgba(29,158,117,0.06)',
              }}
            >
              <Headphones size={21} color="var(--app-success)" />
            </motion.div>
          ) : (
            <motion.div key="connecting">
              {[1, 2, 3].map(ring => (
                <motion.div
                  key={ring}
                  className="absolute rounded-full"
                  style={{ border: '1px solid rgba(244,247,61,0.18)' }}
                  animate={{ width: 52 + ring * 24, height: 52 + ring * 24, opacity: [0.45, 0, 0.45] }}
                  transition={{ duration: 2.4, repeat: Infinity, delay: ring * 0.55, ease: 'easeInOut' }}
                />
              ))}
              <div
                className="relative flex items-center justify-center rounded-full"
                style={{
                  width: 52, height: 52,
                  background: 'rgba(244,247,61,0.06)',
                  border: '1px solid rgba(244,247,61,0.18)',
                }}
              >
                <Headphones size={21} color="var(--yellow-1)" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Text */}
      <AnimatePresence mode="wait">
        {humanConnected ? (
          <motion.div
            key="connected-text"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center flex flex-col gap-2"
          >
            <div className="flex items-center justify-center gap-2 mb-1">
              <span
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full t-caps"
                style={{
                  background: 'rgba(29,158,117,0.08)',
                  border: '1px solid rgba(29,158,117,0.2)',
                  color: 'var(--app-success)',
                  fontSize: '9px',
                }}
              >
                <span className="block w-1.5 h-1.5 rounded-full bg-[var(--app-success)]" />
                Live
              </span>
            </div>
            <p className="t-body-16" style={{ color: '#fff', fontWeight: 500 }}>
              You're connected!
            </p>
            <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.36)', lineHeight: 1.65, maxWidth: 260 }}>
              A Fin support specialist is on the line. They have your full conversation context.
            </p>
          </motion.div>
        ) : (
          <motion.div
            key="connecting-text"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center flex flex-col gap-2"
          >
            <p className="t-body-16" style={{ color: '#fff', fontWeight: 500 }}>
              Connecting you to a specialist
            </p>
            <p className="t-body-14" style={{ color: 'rgba(255,255,255,0.36)', lineHeight: 1.65, maxWidth: 260 }}>
              Please stay on the line — a human agent will join with your full conversation context.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress bars — only while connecting */}
      <AnimatePresence>
        {!humanConnected && (
          <motion.div
            key="bars"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex gap-2 items-end"
            style={{ height: 18 }}
          >
            {[0, 1, 2, 3, 4].map(i => (
              <motion.div
                key={i}
                animate={{ scaleY: [0.18, 1.0, 0.18], opacity: [0.28, 1, 0.28] }}
                transition={{ duration: 0.85, repeat: Infinity, delay: i * 0.14, ease: 'easeInOut' }}
                style={{
                  width: 3, height: 14, borderRadius: 99,
                  background: 'var(--yellow-1)', transformOrigin: 'center',
                }}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Action buttons */}
      <div className="flex flex-col items-center gap-2.5 w-full" style={{ maxWidth: 220 }}>
        {/* "Back to AI" — only visible before human joins */}
        {onRevertToAI && !humanConnected && (
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onRevertToAI}
            className="flex items-center justify-center gap-2 rounded-full t-body-14 w-full"
            style={{
              padding: '10px 22px',
              background: 'rgba(244,247,61,0.05)',
              border: '1px solid rgba(244,247,61,0.18)',
              color: 'rgba(244,247,61,0.8)',
              cursor: 'pointer',
              fontWeight: 500,
              transition: 'all 0.18s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(244,247,61,0.1)'; e.currentTarget.style.color = 'var(--yellow-1)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(244,247,61,0.05)'; e.currentTarget.style.color = 'rgba(244,247,61,0.8)' }}
          >
            <RotateCcw size={12} />
            Back to Fin
          </motion.button>
        )}

        {onEndCall && (
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onEndCall}
            className="flex items-center justify-center gap-2 rounded-full t-body-14 w-full"
            style={{
              padding: '10px 22px',
              background: 'rgba(252,83,91,0.07)',
              border: '1px solid rgba(252,83,91,0.16)',
              color: 'var(--tomato)',
              cursor: 'pointer',
              fontWeight: 500,
              transition: 'background 0.18s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(252,83,91,0.14)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(252,83,91,0.07)' }}
          >
            <PhoneOff size={13} />
            End Call
          </motion.button>
        )}
      </div>
    </div>
  )
}
