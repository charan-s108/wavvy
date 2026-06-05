import { useState, useEffect, useCallback } from 'react'
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
import AgentSelector from './components/coaching/AgentSelector.jsx'
import CoachingPackCard from './components/coaching/CoachingPackCard.jsx'
import GeneratePackButton from './components/coaching/GeneratePackButton.jsx'
import { useSupervisorWS } from './hooks/useSupervisorWS.js'
import AgentConfigPanel from './components/config/AgentConfigPanel.jsx'

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

export default function App() {
  const [page, setPage] = useState('overview')
  const [documents, setDocuments] = useState([])
  const [selectedEval, setSelectedEval] = useState(null)
  const [kbAutoQuery, setKbAutoQuery] = useState('')

  const [agents, setAgents] = useState([])
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [coachingPacks, setCoachingPacks] = useState([])
  const [loadingPacks, setLoadingPacks] = useState(false)

  const { liveCalls, kpis, callHistory, evals, connected, loading, refetchEvals } = useSupervisorWS()

  const fetchDocs = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/kb/documents`)
      if (resp.ok) setDocuments(await resp.json())
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  // Poll every 2s while any document is still processing
  useEffect(() => {
    const hasProcessing = documents.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const timer = setTimeout(fetchDocs, 2000)
    return () => clearTimeout(timer)
  }, [documents, fetchDocs])

  useEffect(() => {
    if (page === 'qa') refetchEvals()
  }, [page, refetchEvals])

  const fetchAgents = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/agents`)
      if (resp.ok) setAgents(await resp.json())
    } catch { /* ignore */ }
  }, [])

  const fetchPacksForAgent = useCallback(async (agentId) => {
    setLoadingPacks(true)
    try {
      const resp = await fetch(`${API}/api/coaching/packs/${agentId}`)
      if (resp.ok) setCoachingPacks(await resp.json())
    } catch { /* ignore */ }
    finally { setLoadingPacks(false) }
  }, [])

  useEffect(() => {
    if (page === 'coaching') fetchAgents()
  }, [page, fetchAgents])

  useEffect(() => {
    if (selectedAgent) fetchPacksForAgent(selectedAgent.agent_id)
  }, [selectedAgent, fetchPacksForAgent])

  return (
    <div className="flex flex-col h-screen" style={{ background: '#000', color: '#fff' }}>
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        <SideNav active={page} onNavigate={setPage} />

        <main className="flex-1 overflow-y-auto px-8 py-8" style={{ background: '#000' }}>
          <div>

            {/* ── OVERVIEW ─────────────────────────────────────── */}
            {page === 'overview' && (
              <div className="flex flex-col gap-6">
                <PageHeader label="Dashboard" title="Overview" />
                <KPIStrip kpis={kpis} />
                <TrendChart data={null} />
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

                {selectedEval && (
                  <div className="flex flex-col gap-4 animate-fade-in">
                    <QAScorecard eval={selectedEval} />
                    <ViolationsList
                      violations={selectedEval.violations}
                      strengths={selectedEval.strengths}
                    />
                  </div>
                )}
              </div>
            )}

            {/* ── COACHING ─────────────────────────────────────── */}
            {page === 'coaching' && (
              <div className="flex flex-col gap-6">
                <PageHeader label="Agent Development" title="Coaching Packs" />

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                  <div className="flex flex-col gap-3">
                    <p className="section-label">Select Agent</p>
                    <AgentSelector
                      agents={agents}
                      selectedId={selectedAgent?.agent_id}
                      onSelect={agent => {
                        setSelectedAgent(agent)
                        setCoachingPacks([])
                      }}
                    />
                  </div>

                  <div className="flex flex-col gap-4">
                    {selectedAgent ? (
                      <>
                        <div className="flex items-center justify-between">
                          <p className="section-label">{selectedAgent.name}</p>
                          <GeneratePackButton
                            agentId={selectedAgent.agent_id}
                            scoredCalls={selectedAgent.scored_calls}
                            onGenerated={pack => setCoachingPacks(prev => [pack, ...prev])}
                          />
                        </div>

                        {loadingPacks ? (
                          <div className="rounded-2xl p-8 text-center"
                            style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                            <p className="t-body-14 text-white/45">Loading packs…</p>
                          </div>
                        ) : coachingPacks.length === 0 ? (
                          <div className="rounded-2xl p-8 text-center"
                            style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                            <p className="t-body-14 text-white/45">
                              No coaching packs yet — click Generate to create one
                            </p>
                          </div>
                        ) : (
                          <div className="flex flex-col gap-4">
                            {coachingPacks.map(pack => (
                              <CoachingPackCard key={pack.pack_id} pack={pack} />
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="rounded-2xl p-8 text-center"
                        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                        <p className="t-body-14 text-white/45">Select an agent to view or generate coaching packs</p>
                      </div>
                    )}
                  </div>
                </div>
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
                <AgentConfigPanel />
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  )
}

function scoreDisplay(score) {
  if (score >= 80) return { color: Y, glow: Ya(0.4) }
  if (score >= 60) return { color: Wa(0.75), glow: Wa(0.12) }
  return { color: Wa(0.40), glow: 'transparent' }
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
