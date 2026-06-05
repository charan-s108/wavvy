import { useState } from 'react'
import { Star } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || ''

export default function FeedbackForm({ callId, onDone }) {
  const [rating,    setRating]    = useState(0)
  const [hovered,   setHovered]   = useState(0)
  const [comment,   setComment]   = useState('')
  const [attempted, setAttempted] = useState(false)

  const submit = () => {
    if (rating === 0) { setAttempted(true); return }

    onDone()  // optimistic close

    if (callId) {
      fetch(`${BACKEND}/api/calls/${callId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating, comment: comment.trim() || null }),
      }).catch(err => console.error('[feedback]', err))
    }
  }

  const display = hovered || rating

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
      className="flex flex-col items-center gap-5 px-6 py-7 flex-1"
    >
      {/* Call ended confirmation */}
      <div className="flex flex-col items-center gap-3 text-center">
        <motion.div
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 400, damping: 22, delay: 0.08 }}
          className="flex items-center justify-center rounded-full"
          style={{
            width: 44, height: 44,
            background: 'rgba(29,158,117,0.07)',
            border: '1px solid rgba(29,158,117,0.18)',
          }}
        >
          <span style={{ fontSize: '18px', color: 'var(--app-success)' }}>✓</span>
        </motion.div>
        <div>
          <p className="t-body-16" style={{ color: '#fff', fontWeight: 500 }}>Call ended</p>
          <p className="t-body-14 mt-1" style={{ color: 'rgba(255,255,255,0.35)' }}>
            Thanks for talking with Fin
          </p>
        </div>
      </div>

      {/* Divider */}
      <div className="w-full" style={{ height: 1, background: 'rgba(255,255,255,0.06)' }} />

      {/* Rating */}
      <div className="flex flex-col items-center gap-4 w-full">
        <div className="text-center">
          <p className="t-body-16" style={{ color: '#fff', fontWeight: 500 }}>How was your experience?</p>
          <p className="t-caps mt-1" style={{ color: 'rgba(255,255,255,0.28)' }}>
            Your feedback helps improve Wavvy
          </p>
        </div>

        {/* Stars */}
        <div className="flex items-center gap-2.5">
          {[1, 2, 3, 4, 5].map(n => (
            <motion.button
              key={n}
              whileTap={{ scale: 0.78 }}
              onClick={() => { setRating(n); setAttempted(false) }}
              onMouseEnter={() => setHovered(n)}
              onMouseLeave={() => setHovered(0)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 3 }}
              aria-label={`${n} star${n > 1 ? 's' : ''}`}
            >
              <motion.div
                animate={{ scale: display >= n ? 1.18 : 1 }}
                transition={{ type: 'spring', stiffness: 500, damping: 22 }}
              >
                <Star
                  size={28}
                  fill={display >= n ? 'var(--yellow-1)' : 'rgba(255,255,255,0.06)'}
                  color={display >= n ? 'var(--yellow-1)' : 'rgba(255,255,255,0.15)'}
                  strokeWidth={1.5}
                />
              </motion.div>
            </motion.button>
          ))}
        </div>

        <AnimatePresence>
          {attempted && rating === 0 && (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="t-caps"
              style={{ color: 'var(--tomato)', marginTop: -6 }}
            >
              Select a rating to submit
            </motion.p>
          )}
        </AnimatePresence>

        {/* Optional comment */}
        <textarea
          value={comment}
          onChange={e => setComment(e.target.value.slice(0, 1000))}
          placeholder="Tell us more… (optional)"
          rows={3}
          className="w-full resize-none outline-none t-body-14"
          style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 10,
            padding: '11px 13px',
            color: '#fff',
            fontFamily: 'Aeonik, system-ui, sans-serif',
            transition: 'border-color 0.2s',
          }}
          onFocus={e => { e.currentTarget.style.borderColor = 'rgba(244,247,61,0.25)' }}
          onBlur={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)' }}
        />

        {/* Submit */}
        <motion.button
          whileTap={{ scale: 0.97 }}
          whileHover={rating > 0 ? { scale: 1.02, y: -1 } : {}}
          onClick={submit}
          className="w-full rounded-full t-body-14"
          style={{
            padding: '13px 0',
            background: rating > 0 ? 'var(--yellow-1)' : 'rgba(244,247,61,0.12)',
            color: rating > 0 ? '#000' : 'rgba(255,255,255,0.25)',
            border: 'none',
            cursor: rating > 0 ? 'pointer' : 'default',
            fontWeight: 500,
            transition: 'all 0.2s',
            boxShadow: rating > 0 ? '0 6px 24px rgba(244,247,61,0.18)' : 'none',
          }}
        >
          Submit Feedback
        </motion.button>
      </div>
    </motion.div>
  )
}
