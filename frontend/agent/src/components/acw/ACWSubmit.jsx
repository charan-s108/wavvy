import { useState } from 'react'
import { CheckCircle, Loader } from 'lucide-react'

export default function ACWSubmit({ acw, onSubmit }) {
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit() {
    setSubmitting(true)
    await onSubmit(acw)
    setSubmitting(false)
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="flex items-center gap-2 justify-center py-3">
        <CheckCircle size={16} color="#f4f73d" />
        <span className="t-body-14" style={{ color: '#f4f73d' }}>ACW Submitted</span>
      </div>
    )
  }

  return (
    <button
      onClick={handleSubmit}
      disabled={submitting || !acw}
      className="w-full py-3 rounded-xl t-body-14 font-medium transition-all hover:opacity-90 disabled:opacity-40"
      style={{ background: '#f4f73d', color: '#000000' }}
    >
      {submitting ? (
        <span className="flex items-center justify-center gap-2">
          <Loader size={14} className="animate-spin" />
          Submitting...
        </span>
      ) : (
        'Submit ACW & Close'
      )}
    </button>
  )
}
