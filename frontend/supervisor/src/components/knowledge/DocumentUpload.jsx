import { useState, useRef } from 'react'
import { Upload, Loader, CheckCircle2, AlertCircle } from 'lucide-react'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'
const ACCEPTED = '.pdf,.docx,.doc,.txt,.md'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

export default function DocumentUpload({ onUploaded }) {
  const [dragging,  setDragging]  = useState(false)
  const [category,  setCategory]  = useState('general')
  const [fileRows,  setFileRows]  = useState([])
  const inputRef = useRef(null)

  async function uploadFile(file, rowId) {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    setFileRows(prev => prev.map(r => r.id === rowId ? { ...r, status: 'uploading' } : r))
    try {
      const resp = await fetch(`${API}/api/kb/upload`, { method: 'POST', body: form })
      const data = await resp.json()
      setFileRows(prev => prev.map(r =>
        r.id === rowId
          ? { ...r, status: resp.ok ? 'done' : 'error', message: resp.ok ? data.message : (data.detail || 'Upload failed') }
          : r
      ))
      if (resp.ok) onUploaded?.()
    } catch {
      setFileRows(prev => prev.map(r => r.id === rowId ? { ...r, status: 'error', message: 'Network error' } : r))
    }
  }

  async function handleFiles(files) {
    if (!files.length) return
    const newRows = Array.from(files).map(f => ({
      id: `${Date.now()}-${Math.random()}`, name: f.name, status: 'pending', message: '', file: f,
    }))
    setFileRows(prev => [...prev, ...newRows])
    for (const row of newRows) await uploadFile(row.file, row.id)
  }

  function onDrop(e) { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }
  function onFileChange(e) { handleFiles(e.target.files); e.target.value = '' }

  const isUploading = fileRows.some(r => r.status === 'uploading' || r.status === 'pending')

  return (
    <div className="flex flex-col gap-4">
      {/* Category */}
      <div className="flex items-center gap-3">
        <span className="t-caps text-white/52 text-[10px]">Category</span>
        <select
          value={category}
          onChange={e => setCategory(e.target.value)}
          className="text-[13px] rounded-xl px-3 py-1.5 outline-none"
          style={{ background: '#1b1d2a', border: `1px solid ${Wa(0.18)}`, color: '#e8e8e8' }}
        >
          <option value="general"            style={{ background: '#1b1d2a', color: '#e8e8e8' }}>General</option>
          <option value="payment_policy"     style={{ background: '#1b1d2a', color: '#e8e8e8' }}>Payment Policy</option>
          <option value="refund_policy"      style={{ background: '#1b1d2a', color: '#e8e8e8' }}>Refund Policy</option>
          <option value="fraud_and_security" style={{ background: '#1b1d2a', color: '#e8e8e8' }}>Fraud & Security</option>
          <option value="kyc_compliance"     style={{ background: '#1b1d2a', color: '#e8e8e8' }}>KYC & Compliance</option>
          <option value="account_support"    style={{ background: '#1b1d2a', color: '#e8e8e8' }}>Account Support</option>
          <option value="dispute_resolution" style={{ background: '#1b1d2a', color: '#e8e8e8' }}>Dispute Resolution</option>
        </select>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className="rounded-2xl flex flex-col items-center justify-center gap-3 py-12 cursor-pointer transition-all"
        style={{
          border: `2px dashed ${dragging ? Ya(0.5) : Wa(0.10)}`,
          background: dragging ? Ya(0.04) : Wa(0.02),
        }}
      >
        {isUploading ? (
          <>
            <Loader size={22} color={Wa(0.38)} className="animate-spin" />
            <p className="text-[13px] text-white/55">Uploading…</p>
          </>
        ) : (
          <>
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: dragging ? Ya(0.10) : Wa(0.05), border: `1px solid ${dragging ? Ya(0.25) : Wa(0.10)}` }}
            >
              <Upload size={18} color={dragging ? Y : Wa(0.45)} />
            </div>
            <div className="text-center">
              <p className="text-[13px] text-white/75">Drop files or click to browse</p>
              <p className="t-caps text-white/40 text-[10px] mt-1">PDF · DOCX · TXT · MD · Max 20 MB</p>
            </div>
          </>
        )}
        <input ref={inputRef} type="file" accept={ACCEPTED} multiple className="hidden" onChange={onFileChange} />
      </div>

      {/* File rows */}
      {fileRows.length > 0 && (
        <div className="flex flex-col gap-2">
          {fileRows.map(row => {
            const isDone = row.status === 'done'
            const isErr  = row.status === 'error'
            const isPending = row.status === 'uploading' || row.status === 'pending'
            return (
              <div
                key={row.id}
                className="flex items-center gap-3 rounded-xl px-4 py-3"
                style={{
                  background: isDone ? Ya(0.04) : isErr ? Wa(0.03) : Wa(0.025),
                  border: `1px solid ${isDone ? Ya(0.15) : isErr ? Wa(0.10) : Wa(0.07)}`,
                }}
              >
                {isPending
                  ? <Loader size={14} color={Wa(0.45)} className="animate-spin flex-shrink-0" />
                  : isDone
                  ? <CheckCircle2 size={14} color={Y} className="flex-shrink-0" />
                  : <AlertCircle  size={14} color={Wa(0.42)} className="flex-shrink-0" />
                }
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] truncate" style={{ color: isDone ? Y : isErr ? Wa(0.55) : Wa(0.75) }}>
                    {row.name}
                  </p>
                  {row.message && <p className="t-caps text-white/38 text-[10px] mt-0.5">{row.message}</p>}
                </div>
                <span
                  className="t-caps text-[10px] flex-shrink-0"
                  style={{ color: isDone ? Y : isPending ? Wa(0.45) : Wa(0.38) }}
                >
                  {row.status}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
