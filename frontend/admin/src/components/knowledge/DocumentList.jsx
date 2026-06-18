import { useState } from 'react'
import { FileText, Trash2, Loader, CheckCircle2, Clock, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import DocumentInspector from './DocumentInspector.jsx'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function statusStyle(status) {
  if (status === 'ready')      return { color: Y,        icon: <CheckCircle2 size={13} color={Y} /> }
  if (status === 'processing') return { color: Wa(0.55), icon: <Loader size={13} color={Wa(0.45)} className="animate-spin" /> }
  if (status === 'error')      return { color: Wa(0.40), icon: <AlertCircle  size={13} color={Wa(0.38)} /> }
  return                              { color: Wa(0.38), icon: <Clock size={13} color={Wa(0.35)} /> }
}

export default function DocumentList({ documents, onDeleted, onQuestionClick }) {
  const [deleting,    setDeleting]    = useState(null)
  const [inspectedId, setInspectedId] = useState(null)

  async function handleDelete(docId) {
    setDeleting(docId)
    if (inspectedId === docId) setInspectedId(null)
    try {
      await fetch(`${API}/api/kb/documents/${docId}`, { method: 'DELETE' })
      onDeleted?.(docId)
    } catch { /* silently fail */ }
    finally { setDeleting(null) }
  }

  if (!documents?.length) {
    return (
      <div
        className="rounded-2xl p-10 flex flex-col items-center justify-center gap-3"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <FileText size={28} color={Wa(0.30)} />
        <p className="t-body-14 text-white/45">No documents uploaded yet</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {documents.map(doc => {
        const { color, icon } = statusStyle(doc.status)
        const isInspected = inspectedId === doc.doc_id

        return (
          <div key={doc.doc_id}>
            <div
              className="flex items-center gap-4 px-4 py-3 transition-all"
              style={{
                background: isInspected ? Ya(0.04) : Wa(0.025),
                border: `1px solid ${isInspected ? Ya(0.16) : Wa(0.07)}`,
                borderRadius: isInspected ? '16px 16px 0 0' : 16,
              }}
            >
              <FileText size={15} color={Wa(0.38)} className="flex-shrink-0" />

              <div className="flex-1 min-w-0">
                <p className="text-[13px] text-white/80 truncate">{doc.filename}</p>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="t-caps text-white/38 text-[10px]">{doc.category}</span>
                  <span className="t-caps text-white/38 text-[10px]">{doc.chunk_count} chunks</span>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                {icon}
                <span className="t-caps text-[10px]" style={{ color }}>{doc.status}</span>
              </div>

              {doc.status === 'ready' && (
                <button
                  onClick={() => setInspectedId(prev => (prev === doc.doc_id ? null : doc.doc_id))}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg t-caps text-[10px] transition-all"
                  style={{
                    background: isInspected ? Ya(0.12) : Wa(0.04),
                    border: `1px solid ${isInspected ? Ya(0.28) : Wa(0.10)}`,
                    color: isInspected ? Y : Wa(0.52),
                  }}
                >
                  Inspect
                  {isInspected ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                </button>
              )}

              <button
                onClick={() => handleDelete(doc.doc_id)}
                disabled={deleting === doc.doc_id}
                className="transition-all disabled:opacity-40"
                style={{ color: Wa(0.30) }}
                onMouseEnter={e => e.currentTarget.style.color = Wa(0.65)}
                onMouseLeave={e => e.currentTarget.style.color = Wa(0.30)}
              >
                {deleting === doc.doc_id
                  ? <Loader size={14} className="animate-spin" />
                  : <Trash2 size={14} />
                }
              </button>
            </div>

            {isInspected && (
              <DocumentInspector
                docId={doc.doc_id}
                filename={doc.filename}
                onQuestionClick={onQuestionClick}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
