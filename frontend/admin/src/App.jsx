import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, Minus, Sparkles, Loader, RefreshCw } from 'lucide-react'
import LoginPage from './LoginPage.jsx'
import TopBar from './components/layout/TopBar.jsx'
import SideNav from './components/layout/SideNav.jsx'
import KPIStrip from './components/overview/KPIStrip.jsx'
import TrendChart from './components/overview/TrendChart.jsx'
import LiveCallsTable from './components/live/LiveCallsTable.jsx'
import CallHistoryTable from './components/history/CallHistoryTable.jsx'
import QAScorecard from './components/qa/QAScorecard.jsx'
import ViolationsList from './components/qa/ViolationsList.jsx'
import DocumentUpload from './components/knowledge/DocumentUpload.jsx'
import DocumentList from './components/knowledge/DocumentList.jsx'
import KBTestSearch from './components/knowledge/KBTestSearch.jsx'
import CoachingPackCard from './components/coaching/CoachingPackCard.jsx'
import { useAdminWS } from './hooks/useAdminWS.js'
import AgentConfigPanel    from './components/config/AgentConfigPanel.jsx'
import WorkflowsPage       from './components/workflows/WorkflowsPage.jsx'
import PromptStudioPage    from './components/prompt-studio/PromptStudioPage.jsx'
import Drawer              from './components/layout/Drawer.jsx'

const API = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function PageHeader({ label, title, right }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-10">
      <div>
        <p className="section-label mb-2.5" style={{ fontSize: 11, letterSpacing: '2px' }}>{label}</p>
        <h1 style={{ fontFamily: "'Orbikular', system-ui, sans-serif", fontWeight: 300, fontSize: 34, lineHeight: 1.15, letterSpacing: '-0.6px', color: '#fff' }}>
          {title}
        </h1>
      </div>
      {right && <div className="flex-shrink-0 pt-2">{right}</div>}
    </div>
  )
}

// ── Auth helpers ────────────────────────────────────────────────────────────

function _loadUser() {
  try {
    const raw = localStorage.getItem('wavvy_admin_info')
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function _isValidSession() {
  const token = localStorage.getItem('wavvy_admin_token')
  const user  = _loadUser()
  if (!token || !user) return false
  if (!['admin'].includes(user.role)) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 > Date.now()
  } catch { return false }
}

// ── Dashboard ───────────────────────────────────────────────────────────────
// All hooks live here so they are never called after a conditional return.

function Dashboard({ user, onLogout }) {
  const [page, setPage] = useState('overview')
  const [documents, setDocuments] = useState([])
  const [selectedEval, setSelectedEval] = useState(null)
  const [kbAutoQuery, setKbAutoQuery] = useState('')

  const [voiceAiStats, setVoiceAiStats]   = useState(null)
  const [voiceAiPacks, setVoiceAiPacks]   = useState([])
  const [loadingStats, setLoadingStats]   = useState(false)
  const [loadingPacks, setLoadingPacks]   = useState(false)
  const [generatingPack, setGeneratingPack] = useState(false)
  const [generateError, setGenerateError]   = useState(null)

  const { liveCalls, kpis, callHistory, evals, connected, loading, refetchEvals } = useAdminWS()

  const fetchDocs = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/kb/documents`)
      if (resp.ok) setDocuments(await resp.json())
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  useEffect(() => {
    const hasProcessing = documents.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const timer = setTimeout(fetchDocs, 2000)
    return () => clearTimeout(timer)
  }, [documents, fetchDocs])

  useEffect(() => {
    if (page === 'qa' || page === 'overview') refetchEvals()
  }, [page, refetchEvals])

  const fetchVoiceAiStats = useCallback(async () => {
    setLoadingStats(true)
    try {
      const resp = await fetch(`${API}/api/coaching/voice-ai/stats`)
      if (resp.ok) setVoiceAiStats(await resp.json())
    } catch { /* ignore */ }
    finally { setLoadingStats(false) }
  }, [])

  const fetchVoiceAiPacks = useCallback(async () => {
    setLoadingPacks(true)
    try {
      const resp = await fetch(`${API}/api/coaching/voice-ai/packs`)
      if (resp.ok) setVoiceAiPacks(await resp.json())
    } catch { /* ignore */ }
    finally { setLoadingPacks(false) }
  }, [])

  useEffect(() => {
    if (page === 'coaching') {
      fetchVoiceAiStats()
      fetchVoiceAiPacks()
    }
  }, [page, fetchVoiceAiStats, fetchVoiceAiPacks])

  return (
    <div className="flex flex-col h-screen" style={{ background: '#000', color: '#fff' }}>
      <TopBar user={user} onLogout={onLogout} />

      <div className="flex flex-1 overflow-hidden">
        <SideNav active={page} onNavigate={setPage} />

        <main className="flex-1 overflow-y-auto px-8 py-8" style={{ background: '#000' }}>
          <div>

            {/* ── OVERVIEW ─────────────────────────────────────── */}
            {page === 'overview' && (
              <div className="flex flex-col gap-6">
                <PageHeader label="Dashboard" title="Overview" />
                <KPIStrip kpis={kpis} />
                <TrendChart evals={evals} />
              </div>
            )}

            {/* ── LIVE CALLS ───────────────────────────────────── */}
            {page === 'live' && (
              <div className="flex flex-col gap-6">
                <PageHeader
                  label="Real-time"
                  title="Live Calls"
                  right={
                    <div className="flex items-center gap-2">
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{
                          background: connected ? Y : Wa(0.35),
                          boxShadow: connected ? `0 0 6px ${Ya(0.7)}` : 'none',
                        }}
                      />
                      <span className="t-caps text-[11px]" style={{ color: connected ? Y : Wa(0.42) }}>
                        {connected ? 'Live' : 'Reconnecting…'}
                      </span>
                    </div>
                  }
                />
                <LiveCallsTable liveCalls={liveCalls} loading={loading} />
              </div>
            )}

            {/* ── HISTORY ──────────────────────────────────────── */}
            {page === 'history' && (
              <div className="flex flex-col gap-6">
                <PageHeader label="Records" title="Call History" />
                <CallHistoryTable calls={callHistory} />
              </div>
            )}

            {/* ── QA SCORES ────────────────────────────────────── */}
            {page === 'qa' && (
              <div className="flex flex-col gap-6">
                <PageHeader
                  label="Quality Assurance"
                  title="QA Scores"
                  right={
                    <span className="t-caps text-white/45 text-[11px]">Updates on call end</span>
                  }
                />

                <div className="flex flex-col gap-2">
                  {evals.length === 0 ? (
                    <div
                      className="rounded-2xl p-10 text-center"
                      style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
                    >
                      <p className="t-body-14 text-white/45">
                        No QA scores yet — scores appear within seconds of a call ending
                      </p>
                    </div>
                  ) : (
                    evals.map(ev => (
                      <EvalRow
                        key={ev.call_id}
                        ev={ev}
                        selected={selectedEval?.call_id === ev.call_id}
                        onSelect={() => setSelectedEval(
                          selectedEval?.call_id === ev.call_id ? null : ev
                        )}
                      />
                    ))
                  )}
                </div>

                <Drawer
                  open={!!selectedEval}
                  onClose={() => setSelectedEval(null)}
                  title={selectedEval?.customer_name || `Call ${selectedEval?.call_id?.slice(0,8)}`}
                  subtitle={selectedEval?.call_started_at
                    ? new Date(selectedEval.call_started_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
                    : undefined}
                  width={520}
                >
                  {selectedEval && (
                    <div className="flex flex-col gap-6">
                      <QAScorecard eval={selectedEval} />
                      <ViolationsList
                        violations={selectedEval.violations}
                        strengths={selectedEval.strengths}
                      />
                    </div>
                  )}
                </Drawer>
              </div>
            )}

            {/* ── COACHING ─────────────────────────────────────── */}
            {page === 'coaching' && (
              <div className="flex flex-col gap-6">
                <PageHeader
                  label="Voice AI Optimization"
                  title="AI Coaching"
                  right={
                    <button
                      onClick={() => { fetchVoiceAiStats(); fetchVoiceAiPacks() }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] transition-opacity hover:opacity-70"
                      style={{ background: Wa(0.05), border: `1px solid ${Wa(0.10)}`, color: Wa(0.55) }}
                    >
                      <RefreshCw size={11} />
                      Refresh
                    </button>
                  }
                />

                {/* Stats row */}
                <VoiceAiStatsRow stats={voiceAiStats} loading={loadingStats} />

                {/* Generate button */}
                <div className="flex items-center justify-between">
                  <p className="section-label">Coaching Packs</p>
                  <VoiceAiGenerateButton
                    stats={voiceAiStats}
                    generating={generatingPack}
                    error={generateError}
                    onGenerate={async () => {
                      setGeneratingPack(true)
                      setGenerateError(null)
                      try {
                        const resp = await fetch(`${API}/api/coaching/voice-ai/generate`, { method: 'POST' })
                        const body = await resp.json()
                        if (!resp.ok) throw new Error(body.detail || `Error ${resp.status}`)
                        setVoiceAiPacks(prev => [body, ...prev])
                        await fetchVoiceAiStats()
                      } catch (err) {
                        setGenerateError(err.message)
                      } finally {
                        setGeneratingPack(false)
                      }
                    }}
                  />
                </div>

                {/* Packs list */}
                {loadingPacks ? (
                  <div className="rounded-2xl p-8 text-center"
                    style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                    <p className="t-body-14 text-white/45">Loading coaching packs…</p>
                  </div>
                ) : voiceAiPacks.length === 0 ? (
                  <div className="rounded-2xl p-10 text-center flex flex-col gap-2 items-center"
                    style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                    <p className="t-body-14 text-white/45">No coaching packs yet</p>
                    <p className="t-caps text-white/28 text-[10px]">
                      {voiceAiStats?.can_generate
                        ? 'Click Generate to analyse recent Voice AI performance'
                        : `${voiceAiStats?.calls_needed ?? 3} more scored call${(voiceAiStats?.calls_needed ?? 3) !== 1 ? 's' : ''} needed before generating`}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-4">
                    {voiceAiPacks.map(pack => (
                      <CoachingPackCard key={pack.pack_id} pack={pack} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── KNOWLEDGE ────────────────────────────────────── */}
            {page === 'knowledge' && (
              <div className="flex flex-col gap-8 max-w-4xl">
                <PageHeader label="Knowledge Management" title="Knowledge Base" />

                <section className="flex flex-col gap-4">
                  <p className="section-label">Upload Document</p>
                  <DocumentUpload onUploaded={fetchDocs} />
                </section>

                <section className="flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <p className="section-label">Indexed Documents</p>
                    <span className="t-caps text-white/45 text-[11px]">{documents.length} docs</span>
                  </div>
                  <DocumentList
                    documents={documents}
                    onDeleted={id => setDocuments(prev => prev.filter(d => d.doc_id !== id))}
                    onQuestionClick={q => setKbAutoQuery(q)}
                  />
                </section>

                <section className="flex flex-col gap-4">
                  <p className="section-label">Test Search</p>
                  <KBTestSearch
                    autoQuery={kbAutoQuery}
                    onAutoQueryConsumed={() => setKbAutoQuery('')}
                  />
                </section>
              </div>
            )}

            {/* ── SETTINGS ─────────────────────────────────────── */}
            {page === 'settings' && (
              <div className="flex flex-col gap-6">
                <PageHeader label="Configuration" title="Agent Settings" />
                <AgentConfigPanel onNavigate={setPage} />
              </div>
            )}

            {/* ── WORKFLOWS ────────────────────────────────────── */}
            {page === 'workflows' && (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <WorkflowsPage />
              </div>
            )}

            {/* ── PROMPTS ──────────────────────────────────────── */}
            {page === 'prompts' && (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <PromptStudioPage />
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  )
}

// ── Root ────────────────────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState(() => _isValidSession() ? _loadUser() : null)

  const handleLogin  = (userData) => setUser(userData)
  const handleLogout = () => {
    localStorage.removeItem('wavvy_admin_token')
    localStorage.removeItem('wavvy_admin_info')
    setUser(null)
  }

  if (!user) return <LoginPage onLogin={handleLogin} />
  return <Dashboard user={user} onLogout={handleLogout} />
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function scoreDisplay(score) {
  if (score >= 80) return { color: Y, glow: Ya(0.4) }
  if (score >= 60) return { color: Wa(0.75), glow: Wa(0.12) }
  return { color: Wa(0.40), glow: 'transparent' }
}

// ── Voice AI Coaching helpers ─────────────────────────────────────────────────

function VoiceAiStatsRow({ stats, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[0,1,2,3].map(i => (
          <div key={i} className="rounded-2xl px-5 py-4 animate-pulse"
            style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
            <div className="h-6 w-10 rounded mb-2" style={{ background: Wa(0.06) }} />
            <div className="h-3 w-16 rounded" style={{ background: Wa(0.04) }} />
          </div>
        ))}
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {['Scored Calls', 'Avg Score', 'Resolution', 'Trend (7d)'].map(label => (
          <div key={label} className="rounded-2xl px-5 py-4"
            style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
            <p className="text-[22px] font-light leading-none mb-1.5" style={{ color: Wa(0.25) }}>—</p>
            <p className="t-caps text-white/28 text-[10px]">{label}</p>
          </div>
        ))}
      </div>
    )
  }

  const trend = stats.trend
  const TrendIcon = trend === 'improving' ? TrendingUp : trend === 'declining' ? TrendingDown : Minus
  const trendColor = trend === 'improving' ? Y : trend === 'declining' ? '#fc535b' : Wa(0.45)

  const tiles = [
    { label: 'Scored Calls',  value: stats.total_scored ?? '—',
      sub: stats.can_generate ? 'Ready to analyse' : `${stats.calls_needed} more needed`,
      subColor: stats.can_generate ? Y : Wa(0.35) },
    { label: 'Avg Score',     value: stats.avg_score != null ? `${stats.avg_score}` : '—',
      sub: stats.pass_rate != null ? `${Math.round(stats.pass_rate * 100)}% pass rate` : null },
    { label: 'Resolution',    value: stats.avg_resolution != null ? `${stats.avg_resolution}` : '—',
      sub: 'avg resolution score' },
    { label: 'Trend (7d)',    value: stats.avg_score_7d != null ? `${stats.avg_score_7d}` : '—',
      sub: trend.charAt(0).toUpperCase() + trend.slice(1),
      subColor: trendColor,
      icon: <TrendIcon size={12} color={trendColor} /> },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {tiles.map(({ label, value, sub, subColor, icon }) => (
        <div key={label} className="rounded-2xl px-5 py-4"
          style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}>
          <p className="text-[22px] font-light text-white leading-none mb-1.5">{value}</p>
          <p className="t-caps text-white/42 text-[10px] mb-1">{label}</p>
          {sub && (
            <p className="flex items-center gap-1 t-caps text-[10px]" style={{ color: subColor || Wa(0.35) }}>
              {icon}{sub}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

function VoiceAiGenerateButton({ stats, generating, error, onGenerate }) {
  const canGenerate = stats?.can_generate && !generating

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={onGenerate}
        disabled={!canGenerate}
        className="flex items-center gap-2 px-4 py-2 rounded-full text-[12px] font-semibold uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: canGenerate ? Y : Wa(0.05),
          color:      canGenerate ? '#000' : Wa(0.38),
          border:     canGenerate ? 'none' : `1px solid ${Wa(0.10)}`,
        }}
        onMouseEnter={e => { if (canGenerate) e.currentTarget.style.opacity = '0.88' }}
        onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
      >
        {generating ? <Loader size={13} className="animate-spin" /> : <Sparkles size={13} />}
        {generating ? 'Analysing…' : 'Generate Pack'}
      </button>
      {!stats?.can_generate && !generating && (
        <p className="t-caps text-white/30 text-[10px]">
          {stats ? `${stats.calls_needed} more scored call${stats.calls_needed !== 1 ? 's' : ''} needed` : 'Loading…'}
        </p>
      )}
      {error && <p className="t-caps text-[10px]" style={{ color: '#fc535b' }}>{error}</p>}
    </div>
  )
}

function EvalRow({ ev, selected, onSelect }) {
  const { color, glow } = scoreDisplay(ev.overall_score)
  const isPassing = ev.pass_fail === 'PASS'

  return (
    <div
      onClick={onSelect}
      className="flex items-center gap-4 rounded-2xl px-4 py-3.5 cursor-pointer transition-all"
      style={{
        background: selected ? Ya(0.05) : Wa(0.02),
        border: `1px solid ${selected ? Ya(0.22) : Wa(0.06)}`,
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = Wa(0.035) }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = Wa(0.02) }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
        style={{
          background: `${color}12`,
          border: `1.5px solid ${color}`,
          boxShadow: `0 0 10px ${glow}`,
        }}
      >
        <span className="text-[13px] font-semibold" style={{ color }}>{ev.overall_score}</span>
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-medium text-white">{ev.customer_name || `Call ${ev.call_id?.slice(0,8)}`}</p>
        <p className="t-caps text-white/42 mt-0.5">
          {ev.call_started_at
            ? new Date(ev.call_started_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
            : '—'}
        </p>
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        <span
          className="t-caps px-2.5 py-1 rounded-full text-[10px]"
          style={{
            color: isPassing ? Y : Wa(0.45),
            background: isPassing ? Ya(0.08) : Wa(0.04),
            border: `1px solid ${isPassing ? Ya(0.22) : Wa(0.10)}`,
          }}
        >
          {ev.pass_fail || '—'}
        </span>
        <span className="t-caps text-white/42 text-[10px] hidden sm:block">{ev.call_resolution || '—'}</span>
      </div>
    </div>
  )
}
