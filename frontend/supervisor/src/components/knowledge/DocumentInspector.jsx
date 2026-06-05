import { useState, useEffect } from 'react'
import { Layers, Grid2X2, HelpCircle, Loader } from 'lucide-react'
import ChunkSimilarityMap from './ChunkSimilarityMap.jsx'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function DocumentInspector({ docId, filename, onQuestionClick }) {
  const [tab,       setTab]       = useState('chunks')
  const [chunks,    setChunks]    = useState([])
  const [questions, setQuestions] = useState([])
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    if (!docId) return
    setLoading(true)
    Promise.all([
      fetch(`${API}/api/kb/chunks/${docId}`).then(r => r.json()).catch(() => []),
      fetch(`${API}/api/kb/questions/${docId}`).then(r => r.json()).catch(() => []),
    ]).then(([c, q]) => {
      setChunks(Array.isArray(c) ? c : [])
      setQuestions(Array.isArray(q) ? q : [])
      setLoading(false)
    })
  }, [docId])

  const tabs = [
    { id: 'chunks',     label: 'Chunks',        Icon: Layers    },
    { id: 'similarity', label: 'Similarity Map', Icon: Grid2X2  },
    { id: 'questions',  label: 'Questions',      Icon: HelpCircle },
  ]

  return (
    <div
      className="overflow-hidden"
      style={{
        background: Wa(0.02),
        border: `1px solid ${Ya(0.12)}`,
        borderTop: 'none',
        borderRadius: '0 0 16px 16px',
      }}
    >
      {/* Tab bar */}
      <div className="flex" style={{ borderBottom: `1px solid ${Wa(0.06)}` }}>
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex items-center gap-1.5 px-4 py-3 t-caps text-[10px] transition-all"
            style={{
              color: tab === id ? Y : Wa(0.42),
              borderBottom: `2px solid ${tab === id ? Y : 'transparent'}`,
              marginBottom: -1,
            }}
          >
            <Icon size={11} />
            {label}
          </button>
        ))}
        <div className="flex-1" />
        {!loading && (
          <div className="flex items-center pr-4">
            <span className="t-caps text-white/35 text-[10px]">
              {chunks.length} chunk{chunks.length !== 1 ? 's' : ''}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {loading ? (
          <div className="flex items-center justify-center gap-3 py-8">
            <Loader size={15} color={Wa(0.35)} className="animate-spin" />
            <p className="text-[13px] text-white/45">Loading…</p>
          </div>
        ) : tab === 'chunks' ? (
          <ChunksTab chunks={chunks} />
        ) : tab === 'similarity' ? (
          <ChunkSimilarityMap docId={docId} />
        ) : (
          <QuestionsTab questions={questions} filename={filename} onQuestionClick={onQuestionClick} />
        )}
      </div>
    </div>
  )
}

function ChunksTab({ chunks }) {
  if (!chunks.length) {
    return (
      <p className="text-[13px] text-white/45 text-center py-6">
        No chunks found — document may still be processing
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2.5 max-h-72 overflow-y-auto pr-1">
      {chunks.map(chunk => (
        <div
          key={chunk.index}
          className="rounded-xl p-3.5"
          style={{ background: Wa(0.03), border: `1px solid ${Wa(0.07)}` }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="t-caps text-[10px]" style={{ color: Y }}>Chunk {chunk.index}</span>
            <div className="flex items-center gap-3">
              <span className="t-caps text-white/38 text-[10px]">{chunk.tokens} tokens</span>
              <span className="t-caps text-white/38 text-[10px]">{chunk.category}</span>
            </div>
          </div>
          <p className="text-[12px] text-white/62 leading-relaxed" style={{ whiteSpace: 'pre-wrap' }}>
            {chunk.content}
          </p>
        </div>
      ))}
    </div>
  )
}

function QuestionsTab({ questions, filename, onQuestionClick }) {
  if (!questions.length) {
    return (
      <div className="py-6 text-center flex flex-col gap-1.5">
        <p className="text-[13px] text-white/45">No headings detected in {filename}</p>
        <p className="t-caps text-white/30 text-[10px]">Headings are extracted from Section / numbered / ALL CAPS structure</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="t-caps text-white/40 text-[10px]">Click a heading to auto-search in the test panel</p>
      <div className="flex flex-wrap gap-2">
        {questions.map((q, i) => (
          <button
            key={i}
            onClick={() => onQuestionClick?.(q)}
            className="px-3 py-1.5 rounded-full text-[11px] transition-all"
            style={{ background: Wa(0.04), border: `1px solid ${Wa(0.10)}`, color: Wa(0.62) }}
            onMouseEnter={e => { e.currentTarget.style.background = Ya(0.07); e.currentTarget.style.borderColor = Ya(0.20); e.currentTarget.style.color = Y }}
            onMouseLeave={e => { e.currentTarget.style.background = Wa(0.04); e.currentTarget.style.borderColor = Wa(0.10); e.currentTarget.style.color = Wa(0.62) }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
