import { useState, useEffect, useCallback } from 'react'
import { Search, Loader } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

const RETRIEVAL_BADGE = {
  dense:  { label: 'Dense',  bg: Wa(0.04),  border: Wa(0.10),  color: Wa(0.62) },
  bm25:   { label: 'BM25',   bg: Ya(0.06),  border: Ya(0.18),  color: Y        },
  graph:  { label: 'Graph',  bg: Wa(0.04),  border: Wa(0.10),  color: Wa(0.62) },
  hybrid: { label: 'Hybrid', bg: Ya(0.04),  border: Ya(0.14),  color: Ya(0.85) },
}

export default function KBTestSearch({ autoQuery, onAutoQueryConsumed }) {
  const [query,     setQuery]     = useState('')
  const [results,   setResults]   = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [questions, setQuestions] = useState([])

  useEffect(() => {
    fetch(`${API}/api/kb/documents`)
      .then(r => r.ok ? r.json() : [])
      .then(docs => {
        const ready = docs.find(d => d.status === 'ready')
        if (!ready) return
        return fetch(`${API}/api/kb/questions/${ready.doc_id}`)
          .then(r => r.ok ? r.json() : [])
          .then(q => setQuestions(Array.isArray(q) ? q : []))
      })
      .catch(() => {})
  }, [])

  const runSearch = useCallback(async (q) => {
    if (!q.trim()) return
    setLoading(true); setResults(null)
    try {
      const resp = await fetch(`${API}/api/kb/search?q=${encodeURIComponent(q.trim())}&n=5`)
      setResults(resp.ok ? await resp.json() : [])
    } catch { setResults([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    if (!autoQuery) return
    setQuery(autoQuery); runSearch(autoQuery); onAutoQueryConsumed?.()
  }, [autoQuery, runSearch, onAutoQueryConsumed])

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={e => { e.preventDefault(); runSearch(query) }} className="flex gap-3">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded-2xl px-4 py-3 text-[13px] text-white outline-none transition-all"
          style={{ background: Wa(0.04), border: `1px solid ${Wa(0.10)}` }}
          onFocus={e => e.currentTarget.style.borderColor = Wa(0.22)}
          onBlur={e  => e.currentTarget.style.borderColor = Wa(0.10)}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="flex items-center gap-2 px-5 py-3 rounded-2xl text-[13px] font-semibold disabled:opacity-40 transition-all"
          style={{ background: Y, color: '#000' }}
          onMouseEnter={e => { if (!loading) e.currentTarget.style.opacity = '0.88' }}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          {loading ? <Loader size={15} className="animate-spin" /> : <Search size={15} />}
          Search
        </button>
      </form>

      {questions.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="section-label text-[10px]">Suggested from document</span>
          <div className="flex flex-wrap gap-2">
            {questions.map((q, i) => (
              <button
                key={i}
                onClick={() => { setQuery(q); runSearch(q) }}
                className="px-3 py-1.5 rounded-full t-caps text-[10px] transition-all"
                style={{ background: Wa(0.04), border: `1px solid ${Wa(0.10)}`, color: Wa(0.62) }}
                onMouseEnter={e => { e.currentTarget.style.background = Ya(0.06); e.currentTarget.style.borderColor = Ya(0.18); e.currentTarget.style.color = Y }}
                onMouseLeave={e => { e.currentTarget.style.background = Wa(0.04); e.currentTarget.style.borderColor = Wa(0.10); e.currentTarget.style.color = Wa(0.62) }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {results !== null && (
        <div className="flex flex-col gap-3">
          {results.length === 0 ? (
            <div
              className="rounded-2xl p-8 text-center"
              style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
            >
              <p className="t-body-14 text-white/45">No results — try different phrasing</p>
            </div>
          ) : (
            results.map((hit, i) => {
              const badge = RETRIEVAL_BADGE[hit.retrieval] || RETRIEVAL_BADGE.dense
              return (
                <div
                  key={i}
                  className="rounded-2xl p-4"
                  style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
                >
                  <div className="flex items-center justify-between mb-2.5 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-medium truncate max-w-xs" style={{ color: Y }}>
                        {hit.source}
                      </span>
                      <span
                        className="t-caps px-2 py-0.5 rounded text-[10px]"
                        style={{ background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color }}
                      >
                        {badge.label}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="t-caps text-white/40 text-[10px]">RRF {hit.rrf_score?.toFixed(4)}</span>
                      <span className="t-caps text-white/40 text-[10px]">{Math.round((hit.relevance || 0) * 100)}% match</span>
                    </div>
                  </div>
                  <p className="text-[13px] text-white/65 leading-relaxed">{hit.content}</p>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
