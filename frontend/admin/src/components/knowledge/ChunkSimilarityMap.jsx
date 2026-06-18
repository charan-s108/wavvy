import { useState, useEffect } from 'react'
import { Loader } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function simToColor(v) {
  // black at 0.0 → yellow at 1.0
  const t = Math.max(0, Math.min(1, v))
  const r = Math.round(244 * t)
  const g = Math.round(247 * t)
  const b = Math.round(61  * t + 8 * (1 - t))
  return `rgb(${r},${g},${b})`
}

export default function ChunkSimilarityMap({ docId }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [tooltip, setTooltip] = useState(null)

  useEffect(() => {
    if (!docId) return
    setLoading(true); setData(null)
    fetch(`${API}/api/kb/similarity/${docId}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [docId])

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-10">
        <Loader size={15} color={Wa(0.35)} className="animate-spin" />
        <p className="text-[13px] text-white/45">Computing similarity…</p>
      </div>
    )
  }

  if (!data || !data.chunks?.length) {
    return (
      <p className="text-[13px] text-white/45 text-center py-6">
        Need at least 2 chunks to render a similarity map
      </p>
    )
  }

  const { chunks, matrix } = data
  const n = Math.min(chunks.length, 30)
  const truncated = chunks.length > 30
  const cellSize  = Math.max(12, Math.min(22, Math.floor(340 / n)))

  return (
    <div className="flex flex-col gap-4">
      {truncated && (
        <p className="t-caps text-white/45 text-[10px]">
          Showing first 30 of {chunks.length} chunks
        </p>
      )}

      <div className="overflow-x-auto">
        <div className="flex gap-2">
          {/* Row labels */}
          <div className="flex flex-col" style={{ marginTop: cellSize + 4 }}>
            {chunks.slice(0, n).map((_, i) => (
              <div
                key={i}
                className="flex items-center justify-end"
                style={{ height: cellSize + 1, fontSize: 9, paddingRight: 4, minWidth: 20, color: Wa(0.35) }}
              >
                {i}
              </div>
            ))}
          </div>

          <div>
            {/* Column labels */}
            <div className="flex" style={{ marginBottom: 4 }}>
              {chunks.slice(0, n).map((_, i) => (
                <div key={i} style={{ width: cellSize + 1, textAlign: 'center', fontSize: 9, color: Wa(0.35) }}>
                  {i}
                </div>
              ))}
            </div>

            {/* N×N grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${n}, ${cellSize}px)`,
                gap: 1,
              }}
            >
              {matrix.slice(0, n).flatMap((row, i) =>
                row.slice(0, n).map((val, j) => (
                  <div
                    key={`${i}-${j}`}
                    style={{
                      width: cellSize, height: cellSize,
                      background: simToColor(val),
                      borderRadius: 2,
                      cursor: 'crosshair',
                      opacity: val === 1 && i === j ? 1 : undefined,
                    }}
                    onMouseEnter={() => setTooltip({ i, j, val })}
                    onMouseLeave={() => setTooltip(null)}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Legend + tooltip */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div
            style={{
              width: 72, height: 6,
              background: `linear-gradient(to right, #0a0a0a, ${Y})`,
              borderRadius: 3,
            }}
          />
          <span className="t-caps text-white/38 text-[10px]">unrelated → near-duplicate</span>
        </div>
        <span className="t-caps text-white/38 text-[10px]">
          {tooltip
            ? `Chunk ${tooltip.i} × ${tooltip.j}: ${tooltip.val.toFixed(3)}`
            : 'hover a cell to inspect'}
        </span>
      </div>

      <p className="t-caps text-white/35 text-[10px]">
        Bright yellow off-diagonal cells = near-duplicate chunks — consider adjusting chunk size
      </p>
    </div>
  )
}
