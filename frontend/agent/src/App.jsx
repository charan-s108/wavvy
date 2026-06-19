import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Phone, PhoneOff, Send,
  Sparkles, ShieldCheck, Zap, AlertCircle, CheckCircle2,
  Activity, ChevronDown, RefreshCw, CheckCheck,
  BookOpen, Lightbulb, ArrowRight, LogOut, MessageSquare,
} from 'lucide-react'
import { useAgentWebSocket } from './hooks/useAgentWebSocket.js'
import LoginPage             from './LoginPage.jsx'
import HandoffCard           from './components/console/HandoffCard.jsx'
import DataAlerts            from './components/companion/DataAlerts.jsx'
import CaseAnalysis          from './components/companion/CaseAnalysis.jsx'
import Timeline              from './components/companion/Timeline.jsx'
import LiveDocumentation     from './components/companion/LiveDocumentation.jsx'
// SIM — remove this import to disable simulation
import { useSimulation, SIM_STEP_LABELS }  from './simulation.js'

const BACKEND = import.meta.env.VITE_BACKEND_HTTP_URL || ''

/* ── Palette ─────────────────────────────────────────────────
   Three colors only: #000000 · #ffffff · #f4f73d
   ─────────────────────────────────────────────────────────── */

const Y = '#f4f73d'          // brand yellow
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

const MOOD_COLOR = {
  frustrated: Wa(0.9),
  angry:      Wa(0.9),
  curious:    Y,
  satisfied:  Y,
  calm:       Wa(0.65),
}

const STATUS_CONFIG = {
  active:   { label: 'Active',   dot: Y,        glow: Ya(0.5), text: '' },
  busy:     { label: 'Busy',     dot: Wa(0.45), glow: Wa(0.2), text: '' },
  inactive: { label: 'Inactive', dot: Wa(0.18), glow: 'transparent', text: '' },
}

function tsNow() {
  return new Date().toTimeString().split(' ')[0]
}

function initials(name = '') {
  return name.split(' ').map(p => p[0] || '').join('').toUpperCase().slice(0, 2)
}

/* ══════════════════════════════════════════════════════════════
   TOOLKIT PANEL — manual action control for agents
   All actions go through the same sendActionApproved WebSocket
   path as companion-suggested actions; backend auto-enriches
   customer_id from ACTIVE_CALLS.
═══════════════════════════════════════════════════════════════ */
const TOOLKIT_GROUPS = [
  {
    label: 'Identity Verification',
    color: '#9543f6',
    actions: [
      { id: 'send_otp_to_customer',  label: 'Send OTP',      icon: '📨', params: [] },
      { id: 'verify_customer_otp',   label: 'Verify OTP',    icon: '🔑', params: [{ key: 'otp_code', label: 'OTP Code', placeholder: '6-digit code', type: 'text', maxLength: 6 }] },
    ],
  },
  {
    label: 'Account',
    color: '#fabc2d',
    actions: [
      { id: 'unlock_account',   label: 'Unlock Account',     icon: '🔓', params: [] },
      { id: 'remove_fraud_hold', label: 'Remove Fraud Hold', icon: '🛡', params: [] },
      { id: 'freeze_account',   label: 'Freeze Account',     icon: '❄', params: [] },
      { id: 'reset_2fa',        label: 'Reset 2FA',          icon: '🔄', params: [] },
      { id: 'mark_kyc_verified', label: 'Mark KYC Verified', icon: '✅', params: [] },
    ],
  },
  {
    label: 'Payments',
    color: '#1D9E75',
    actions: [
      { id: 'issue_refund',    label: 'Issue Refund',    icon: '💸', params: [{ key: 'transaction_id', label: 'TXN ID', placeholder: 'TXN-XXXX', type: 'text' }] },
      { id: 'reopen_dispute',  label: 'Reopen Dispute',  icon: '📋', params: [{ key: 'dispute_number', label: 'Dispute #', placeholder: 'DSP-XXXX', type: 'text' }] },
    ],
  },
  {
    label: 'Fraud',
    color: '#fc535b',
    actions: [
      { id: 'escalate_fraud_team', label: 'Escalate Fraud Team', icon: '🚨', params: [] },
    ],
  },
]

function ToolkitPanel({ callId, customer, toolkitStatuses, toolkitMessages, toolkitRefs,
                        toolkitParams, setToolkitParams, toolkitExpanded, setToolkitExpanded,
                        fireToolkitAction }) {
  const noCall = !callId
  return (
    <div className="flex flex-col gap-4">
      {/* Header hint */}
      <div className="rounded-xl p-3 flex items-start gap-2.5"
        style={{ background: 'rgba(149,67,246,0.06)', border: '1px solid rgba(149,67,246,0.14)' }}>
        <span className="text-[13px] mt-0.5">🛠</span>
        <div>
          <p className="text-[12px] font-semibold text-white/80">Manual Agent Toolkit</p>
          <p className="text-[11px] text-white/45 mt-0.5 leading-snug">
            {noCall ? 'Available when a call is active.' : `Actions run on ${customer?.name || 'this customer'}'s account.`}
          </p>
        </div>
      </div>

      {TOOLKIT_GROUPS.map(group => (
        <div key={group.label}>
          <p className="text-[10px] font-semibold uppercase tracking-widest mb-2"
            style={{ color: group.color, opacity: 0.75 }}>{group.label}</p>
          <div className="space-y-1.5">
            {group.actions.map(action => {
              const status  = toolkitStatuses[action.id] || 'idle'
              const message = toolkitMessages[action.id] || ''
              const refs    = toolkitRefs[action.id]
              const isExpanded = toolkitExpanded === action.id && action.params.length > 0
              const paramVals  = toolkitParams[action.id] || {}

              return (
                <div key={action.id} className="rounded-xl overflow-hidden"
                  style={{ border: `1px solid ${status === 'ok' ? 'rgba(29,158,117,0.25)' : status === 'err' ? 'rgba(252,83,91,0.25)' : 'rgba(255,255,255,0.07)'}`, background: 'rgba(255,255,255,0.02)' }}>
                  <button
                    disabled={noCall || status === 'running'}
                    onClick={() => {
                      if (action.params.length === 0) {
                        fireToolkitAction(action.id, {})
                      } else {
                        setToolkitExpanded(prev => prev === action.id ? null : action.id)
                      }
                    }}
                    className="w-full flex items-center justify-between px-3 py-2.5 transition-all disabled:opacity-40"
                    style={{ cursor: noCall || status === 'running' ? 'not-allowed' : 'pointer' }}>
                    <div className="flex items-center gap-2">
                      <span className="text-[13px]">{action.icon}</span>
                      <span className="text-[12px] font-medium text-white/85">{action.label}</span>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md"
                      style={{
                        background: status === 'ok' ? 'rgba(29,158,117,0.12)' : status === 'err' ? 'rgba(252,83,91,0.10)' : status === 'running' ? 'rgba(244,247,61,0.08)' : 'rgba(255,255,255,0.05)',
                        color:      status === 'ok' ? '#1D9E75' : status === 'err' ? '#fc535b' : status === 'running' ? '#f4f73d' : 'rgba(255,255,255,0.35)',
                      }}>
                      {status === 'running' ? '…' : status === 'ok' ? '✓' : status === 'err' ? '✗' : action.params.length > 0 ? '›' : 'Run'}
                    </span>
                  </button>

                  {/* Inline param form */}
                  {isExpanded && (
                    <div className="px-3 pb-3 space-y-2 border-t border-white/[0.06]">
                      {action.params.map(p => (
                        <div key={p.key} className="flex flex-col gap-1 pt-2">
                          <label className="text-[10px] text-white/45">{p.label}</label>
                          <input
                            type={p.type || 'text'}
                            maxLength={p.maxLength}
                            placeholder={p.placeholder}
                            value={paramVals[p.key] || ''}
                            onChange={e => setToolkitParams(prev => ({
                              ...prev, [action.id]: { ...(prev[action.id] || {}), [p.key]: e.target.value }
                            }))}
                            className="w-full px-2.5 py-1.5 rounded-lg text-[12px] text-white bg-transparent outline-none font-mono"
                            style={{ border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)' }}
                          />
                        </div>
                      ))}
                      <button
                        onClick={() => fireToolkitAction(action.id, paramVals)}
                        className="w-full mt-1 py-1.5 rounded-lg text-[11px] font-semibold transition-all"
                        style={{ background: 'rgba(149,67,246,0.12)', color: '#9543f6', border: '1px solid rgba(149,67,246,0.22)' }}>
                        Execute
                      </button>
                    </div>
                  )}

                  {/* Result / reference numbers */}
                  {(message || refs) && (
                    <div className="px-3 pb-2.5">
                      {message && <p className="text-[11px] text-white/55 leading-snug">{message}</p>}
                      {refs && (
                        <p className="text-[11px] font-mono mt-1" style={{ color: '#f4f73d' }}>
                          {Object.values(refs).join(' · ')}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function AgentDesktop() {
  /* ── Auth ─────────────────────────────────────────────────── */
  const [agentInfo, setAgentInfo] = useState(() => {
    try { return JSON.parse(localStorage.getItem('wavvy_agent_info') || 'null') } catch { return null }
  })
  const handleLogin  = useCallback((info) => setAgentInfo(info), [])
  const handleLogout = useCallback(() => {
    localStorage.removeItem('wavvy_agent_token')
    localStorage.removeItem('wavvy_agent_info')
    setAgentInfo(null)
  }, [])

  /* ── Agent status ─────────────────────────────────────────── */
  const [agentStatus, setAgentStatus] = useState('active')

  /* ── Call state ───────────────────────────────────────────── */
  // Restore from localStorage immediately on mount so there's no idle flash after refresh
  const [callerState, setCallerState] = useState(() => {
    try {
      const s = localStorage.getItem('wavvy_call_state')
      if (s) { const d = JSON.parse(s); if (d?.callId) return 'incoming' }
    } catch {}
    return 'idle'
  })
  const [activeTab,   setActiveTab]   = useState('conversation')
  const [callId,      setCallId]      = useState(() => {
    try { const s = localStorage.getItem('wavvy_call_state'); return JSON.parse(s)?.callId || null } catch { return null }
  })

  const [customer, setCustomer] = useState(() => {
    try { const s = localStorage.getItem('wavvy_call_state'); return JSON.parse(s)?.customer || null } catch { return null }
  })
  const [handoff,  setHandoff]  = useState(() => {
    try { const s = localStorage.getItem('wavvy_call_state'); return JSON.parse(s)?.handoff || null } catch { return null }
  })
  const [voiceTx,  setVoiceTx]  = useState(() => {
    try { const s = localStorage.getItem('wavvy_call_state'); return JSON.parse(s)?.voiceTx || [] } catch { return [] }
  })
  const [liveTx,   setLiveTx]   = useState([])
  const [chatInput,    setChatInput]    = useState('')
  const [quickReplies, setQuickReplies] = useState([])

  /* ── Companion ────────────────────────────────────────────── */
  const [checklist,         setChecklist]         = useState([])
  const [nudge,             setNudge]             = useState(null)
  const [nextAction,        setNextAction]        = useState('')
  const [customerMood,      setCustomerMood]      = useState('calm')
  const [kbSuggestion,      setKbSuggestion]      = useState(null)
  const [insight,           setInsight]           = useState(null)

  /* ── Elite Companion — new fields ────────────────────────── */
  const [suggestedActions,  setSuggestedActions]  = useState([])
  // actionStatuses: { [action_id + executionId]: 'pending'|'executing'|'completed'|'failed'|'rejected' }
  const [actionStatuses,    setActionStatuses]    = useState({})
  const [activityTimeline,  setActivityTimeline]  = useState([])
  const [sentimentHistory,  setSentimentHistory]  = useState([])  // [{mood}]
  const [resolutionProb,    setResolutionProb]    = useState(null)
  const [sentimentTrend,    setSentimentTrend]    = useState('stable')
  const [riskFlags,         setRiskFlags]         = useState([])
  const [acwPreview,        setAcwPreview]        = useState(null)
  const [timelineOpen,      setTimelineOpen]      = useState(false)
  const [acwPreviewOpen,    setAcwPreviewOpen]    = useState(false)
  // OTP input state: keyed by action.id so each card is independent
  const [otpInputs,         setOtpInputs]         = useState({})

  /* ── Manual Agent Toolkit ─────────────────────────────────── */
  const [rightTab,          setRightTab]          = useState('companion')  // 'companion' | 'toolkit'
  const [toolkitStatuses,   setToolkitStatuses]   = useState({})   // {actionName: 'idle'|'running'|'ok'|'err'}
  const [toolkitMessages,   setToolkitMessages]   = useState({})   // {actionName: string}
  const [toolkitRefs,       setToolkitRefs]       = useState({})   // {actionName: reference_numbers}
  const [toolkitParams,     setToolkitParams]     = useState({})   // {actionName: {paramKey: value}}
  const [toolkitExpanded,   setToolkitExpanded]   = useState(null) // which action row is expanded
  // Account update form state: keyed by action.id
  const [acctUpdateInputs,  setAcctUpdateInputs]  = useState({})

  /* ── Case Intelligence ────────────────────────────────────── */
  const [caseInvestigation, setCaseInvestigation] = useState(null)
  const [openQuestions,     setOpenQuestions]     = useState([])
  const [liveDoc,           setLiveDoc]           = useState(null)

  /* ── Resizable columns ────────────────────────────────────── */
  const [leftWidth,  setLeftWidth]  = useState(() => parseInt(localStorage.getItem('wavvy_col_left')  || '260'))
  const [rightWidth, setRightWidth] = useState(() => parseInt(localStorage.getItem('wavvy_col_right') || '320'))
  const leftWidthRef  = useRef(leftWidth)
  const rightWidthRef = useRef(rightWidth)
  useEffect(() => { leftWidthRef.current  = leftWidth  }, [leftWidth])
  useEffect(() => { rightWidthRef.current = rightWidth }, [rightWidth])

  const startDrag = useCallback((side, e) => {
    e.preventDefault()
    const startX     = e.clientX
    const startLeft  = leftWidthRef.current
    const startRight = rightWidthRef.current
    document.body.style.cursor     = 'col-resize'
    document.body.style.userSelect = 'none'

    const onMove = (ev) => {
      const dx = ev.clientX - startX
      if (side === 'left') {
        const w = Math.max(180, Math.min(480, startLeft + dx))
        setLeftWidth(w); leftWidthRef.current = w
      } else {
        const w = Math.max(220, Math.min(560, startRight - dx))
        setRightWidth(w); rightWidthRef.current = w
      }
    }
    const onUp = () => {
      document.body.style.cursor     = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup',   onUp)
      localStorage.setItem('wavvy_col_left',  String(leftWidthRef.current))
      localStorage.setItem('wavvy_col_right', String(rightWidthRef.current))
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup',   onUp)
  }, [])

  /* ── ACW ──────────────────────────────────────────────────── */
  const [acwData,      setAcwData]      = useState(null)
  const [summaryText,  setSummaryText]  = useState('')
  const [resolution,   setResolution]   = useState('resolved')
  const [acwSubmitted, setAcwSubmitted] = useState(false)

  const chatBottom   = useRef(null)
  const chatInputRef = useRef(null)
  useEffect(() => { chatBottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [liveTx])

  /* ── WebSocket handlers ───────────────────────────────────── */
  const onIncomingCall = useCallback((msg) => {
    const bundle  = msg.handoff_bundle || {}
    const lead    = bundle.lead || {}
    const SENTIMENT_TO_MOOD = { positive: 'satisfied', neutral: 'calm', negative: 'frustrated' }
    const customer = {
      name:           lead.name  || 'Customer',
      email:          lead.email || '',
      phone:          lead.phone || '',
      intent:         (lead.intent || '').replace(/_/g, ' '),
      account_type:   lead.account_type || '',
      account_status: lead.account_status || 'active',
      kyc_status:     lead.kyc_status || '',
      fraud_hold:     lead.fraud_hold_active || false,
    }
    const handoff  = { reason: bundle.reason || 'Customer request' }
    const voiceTx  = (msg.voice_transcript || []).map(l => ({ ...l, time: l.time || tsNow() }))

    setCallId(msg.call_id)
    setCustomer(customer)
    setHandoff(handoff)
    setVoiceTx(voiceTx)
    setLiveTx([])
    setQuickReplies([])
    setChecklist([]); setNudge(null)
    setNextAction('Greet the customer and acknowledge the AI handoff')
    setCustomerMood(SENTIMENT_TO_MOOD[lead.sentiment_status] || 'calm')
    setKbSuggestion(null); setInsight(null)
    setSuggestedActions([]); setActionStatuses({}); setActivityTimeline([])
    setSentimentHistory([]); setResolutionProb(null); setSentimentTrend('stable')
    setRiskFlags([]); setAcwPreview(null)
    setAcwData(null); setSummaryText(''); setResolution('resolved'); setAcwSubmitted(false)
    setCaseInvestigation(null); setOpenQuestions([]); setLiveDoc(null)
    setCallerState('incoming')

    // Persist so page refresh restores the incoming-call banner immediately,
    // without waiting for the WebSocket to reconnect and re-deliver.
    try {
      localStorage.setItem('wavvy_call_state', JSON.stringify({
        callId: msg.call_id, customer, handoff, voiceTx, savedAt: Date.now(),
      }))
    } catch {}
  }, [])

  const onTranscript = useCallback((speaker, text, isFinal) => {
    if (!isFinal) return
    setLiveTx(prev => {
      // Dedup: same speaker+text within 3s — prevents LiveKit data channel + WS double-delivery
      // NOTE: use m.ts (Unix ms), NOT m.time (display string) for numeric comparison
      const cutoff = Date.now() - 3000
      if (prev.some(m => m.speaker === speaker && m.text === text && (m.ts || 0) > cutoff)) return prev
      return [...prev, { speaker, text, time: tsNow(), ts: Date.now() }]
    })
  }, [])

  const onCompanionUpdate = useCallback((msg) => {
    if (Array.isArray(msg.checklist) && msg.checklist.length) setChecklist(msg.checklist)
    if ('nudge'         in msg) setNudge(msg.nudge)
    if (msg.next_action)        setNextAction(msg.next_action)
    if (msg.customer_mood) {
      setCustomerMood(msg.customer_mood)
      setSentimentHistory(prev => [...prev.slice(-9), { mood: msg.customer_mood }])
    }
    if ('kb_suggestion' in msg) setKbSuggestion(msg.kb_suggestion)
    if ('insight'       in msg) setInsight(msg.insight)
    // Elite fields
    if (Array.isArray(msg.quick_replies)) setQuickReplies(msg.quick_replies)
    if (Array.isArray(msg.suggested_actions) && msg.suggested_actions.length > 0) {
      setSuggestedActions(msg.suggested_actions)
      msg.suggested_actions.forEach(a => {
        setActionStatuses(prev => prev[a.id] ? prev : { ...prev, [a.id]: 'pending' })
        setActivityTimeline(prev => [
          ...prev,
          { time: tsNow(), kind: 'suggested', action: a.id, message: `AI suggested: ${a.label}` },
        ])
      })
    }
    // empty suggested_actions list intentionally not cleared — existing cards drain
    // naturally when the agent approves/rejects them
    if (msg.resolution_probability != null) setResolutionProb(msg.resolution_probability)
    if (msg.sentiment_trend) setSentimentTrend(msg.sentiment_trend)
    if (Array.isArray(msg.risk_flags))  setRiskFlags(msg.risk_flags)
    if (msg.acw_preview?.summary)       setAcwPreview(msg.acw_preview)
    // Case Intelligence live updates
    if (msg.documentation_update?.summary) {
      setLiveDoc(prev => ({
        ...(prev || {}),
        summary: msg.documentation_update.summary,
        action_items: [...(prev?.action_items || []), ...(msg.documentation_update.action_items || [])],
      }))
    }
    if (Array.isArray(msg.new_open_questions) && msg.new_open_questions.length) {
      setOpenQuestions(prev => {
        const existing = new Set(prev.map(q => (typeof q === 'string' ? q : q.question)))
        const newOnes = msg.new_open_questions.filter(q => !existing.has(typeof q === 'string' ? q : q.question))
        return newOnes.length ? [...prev, ...newOnes] : prev
      })
    }
    if (Array.isArray(msg.resolved_questions) && msg.resolved_questions.length) {
      setOpenQuestions(prev => prev.filter(q => {
        const text = typeof q === 'string' ? q : q.question
        return !msg.resolved_questions.includes(text)
      }))
    }
  }, [])

  const onAcwReady = useCallback((msg) => {
    setAcwData(msg)
    setSummaryText(msg.summary   || '')
    setResolution(msg.resolution || 'resolved')
    setCallerState('acw')
  }, [])

  const onCallClosed = useCallback(() => {
    try { localStorage.removeItem('wavvy_call_state') } catch {}
    setCallerState('acw')
    if (!acwData) setSummaryText('Call ended — generating summary…')
  }, [acwData])

  const onCustomerTranscript = useCallback((text) => {
    setLiveTx(prev => {
      // Dedup: same-room escalation delivers customer speech via both LiveKit data channel
      // and the backend WS — drop the duplicate within a 3s window.
      const cutoff = Date.now() - 3000
      if (prev.some(m => m.speaker === 'customer' && m.text === text && (m.ts || 0) > cutoff)) return prev
      return [...prev, { speaker: 'customer', text, time: tsNow(), ts: Date.now() }]
    })
  }, [])

  const onStatusUpdated = useCallback((s) => setAgentStatus(s), [])

  const onActionResult = useCallback((msg) => {
    const key = msg.action
    const refs = msg.reference_numbers && Object.keys(msg.reference_numbers).length > 0
      ? msg.reference_numbers : null
    setActionStatuses(prev => ({ ...prev, [key]: msg.success ? 'completed' : 'failed' }))
    // Toolkit panel status
    setToolkitStatuses(prev => ({ ...prev, [key]: msg.success ? 'ok' : 'err' }))
    setToolkitMessages(prev => ({ ...prev, [key]: msg.message || (msg.success ? 'Done' : 'Failed') }))
    if (refs) setToolkitRefs(prev => ({ ...prev, [key]: refs }))
    if (msg.success) {
      setToolkitExpanded(prev => prev === key ? null : prev)  // collapse on success
      setActivityTimeline(prev => [
        ...prev,
        { time: tsNow(), kind: 'action_executed', action: msg.action, message: msg.message || 'Action completed', reference_numbers: refs },
      ])
    }
  }, [])

  const onActivityEvent = useCallback((msg) => {
    setActivityTimeline(prev => [
      ...prev,
      { time: tsNow(), kind: msg.kind, action: msg.action, message: msg.message || '' },
    ])
  }, [])

  const onCaseInvestigation = useCallback((msg) => {
    setCaseInvestigation(msg)
    if (Array.isArray(msg.open_questions)) setOpenQuestions(msg.open_questions)
    if (msg.live_documentation?.summary) setLiveDoc(msg.live_documentation)
  }, [])

  const onSentimentUpdate = useCallback((msg) => {
    if (msg.mood) {
      setCustomerMood(msg.mood)
      setSentimentHistory(prev => [...prev.slice(-9), { mood: msg.mood }])
    }
  }, [])

  const {
    sendEndCall, sendAcwSubmit, sendSetStatus, sendDeclineCall,
    sendActionApproved, sendActionRejected,
  } = useAgentWebSocket({
    onIncomingCall, onTranscript, onCompanionUpdate, onAcwReady, onCallClosed, onStatusUpdated,
    onAuthError: handleLogout, onActionResult, onActivityEvent,
    onCaseInvestigation, onSentimentUpdate,
  })

  const handleStatusChange = useCallback((s) => {
    setAgentStatus(s); sendSetStatus(s)
  }, [sendSetStatus])

  // Send text to customer via TTS (agent types → backend plays via agent_session.say)
  const sendAgentMessage = useCallback(async (text) => {
    if (!text?.trim() || !callId) return
    const trimmed = text.trim()
    // Optimistic UI
    setLiveTx(prev => {
      const cutoff = Date.now() - 2000
      if (prev.some(m => m.speaker === 'agent' && m.text === trimmed && (m.ts || 0) > cutoff)) return prev
      return [...prev, { speaker: 'agent', text: trimmed, time: tsNow(), ts: Date.now() }]
    })
    setQuickReplies([])
    try {
      await fetch(`${BACKEND}/api/calls/${callId}/agent-say`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      })
    } catch {}
  }, [callId])

  // SIM — remove this block to disable simulation
  const { runSimulation, nextStep, clearSim, simStep, simActive, simTotalSteps } = useSimulation({
    setCallerState, setCallId, setCustomer, setHandoff,
    setVoiceTx, setLiveTx,
    setQuickReplies,
    setChecklist, setNudge, setNextAction, setCustomerMood,
    setKbSuggestion, setInsight,
    setAcwData, setSummaryText, setResolution, setAcwSubmitted,
    setSuggestedActions, setActionStatuses,
    setActivityTimeline, setSentimentHistory,
    setResolutionProb, setSentimentTrend,
    setRiskFlags, setAcwPreview,
    setCaseInvestigation, setOpenQuestions, setLiveDoc,
    setRightTab, setToolkitStatuses, setToolkitMessages, setToolkitRefs,
  })
  useEffect(() => () => clearSim(), [clearSim])

  // SIM — Space / Enter → next step · Escape → exit demo
  // Only fires when focus is NOT on an interactive element (the button handles its own Space)
  useEffect(() => {
    if (!simActive) return
    const handler = (e) => {
      const tag = document.activeElement?.tagName
      const isInteractive = tag === 'BUTTON' || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
      if (isInteractive) return   // let the focused element handle it natively
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); nextStep() }
      if (e.key === 'Escape') clearSim()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [simActive, nextStep, clearSim])

  /* ── Call lifecycle ───────────────────────────────────────── */
  const handleChatSend = useCallback(() => {
    const text = chatInput.trim()
    if (!text) return
    setChatInput('')
    sendAgentMessage(text)
    chatInputRef.current?.focus()
  }, [chatInput, sendAgentMessage])

  const handleAcceptCall = useCallback(async () => {
    setLiveTx([{ speaker: 'system', text: `Call connected — ${customer?.name || 'Customer'} is on the line.`, time: tsNow(), ts: Date.now() }])
    setCallerState('active')
    // Notify backend → worker sets session.human_joined=True → publishes human_agent_joined
    // to the customer's browser (TransferScreen → CallScreen) AND unlocks agent-say TTS.
    if (callId) {
      try {
        await fetch(`${BACKEND}/api/livekit/agent-join`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ call_id: callId }),
        })
      } catch {}
    }
  }, [callId, customer])

  const handleEndCall = () => {
    sendEndCall(callId)   // callId included so backend can always find the session
    // Optimistic: transition immediately so the button doesn't freeze.
    // onAcwReady will update summaryText when the backend responds.
    setCallerState('acw')
    if (!acwData) setSummaryText('Call ended — generating summary…')
    if (callId) fetch(`${BACKEND}/api/calls/${callId}/end`, { method: 'POST' }).catch(() => {})
  }

  const handleDeclineCall = useCallback(() => {
    if (callId) sendDeclineCall(callId)
    try { localStorage.removeItem('wavvy_call_state') } catch {}
    setCallerState('idle'); setCustomer(null); setCallId(null)
  }, [callId, sendDeclineCall])

  const handleAcwSubmit = (e) => {
    e.preventDefault()
    sendAcwSubmit({ summary: summaryText, resolution, crm_fields: acwData?.crm_fields || {} })
    try { localStorage.removeItem('wavvy_call_state') } catch {}
    setAcwSubmitted(true)
    setTimeout(() => {
      setCallerState('idle')
      setCustomer(null); setHandoff(null); setCallId(null)
      setLiveTx([]); setVoiceTx([])
      setQuickReplies([])
      setChecklist([]); setNudge(null); setNextAction('')
      setKbSuggestion(null); setInsight(null)
      setSuggestedActions([]); setActionStatuses({}); setActivityTimeline([])
      setSentimentHistory([]); setResolutionProb(null); setSentimentTrend('stable')
      setRiskFlags([]); setAcwPreview(null)
      setCaseInvestigation(null); setOpenQuestions([]); setLiveDoc(null)
    }, 1600)
  }

  const toggleChecklistItem = (idx) =>
    setChecklist(prev => prev.map((item, i) => i === idx ? { ...item, done: !item.done } : item))

  const handleApproveAction = useCallback((action) => {
    const execId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `exec-${Date.now()}-${Math.random().toString(36).slice(2)}`
    setActionStatuses(prev => ({ ...prev, [action.id]: 'executing' }))
    setActivityTimeline(prev => [
      ...prev,
      { time: tsNow(), kind: 'action_approved', action: action.id, message: `Agent approved: ${action.label}` },
    ])
    sendActionApproved(action.id, action.payload || {}, execId, callId)
  }, [sendActionApproved, callId])

  const handleRejectAction = useCallback((action) => {
    setActionStatuses(prev => ({ ...prev, [action.id]: 'rejected' }))
    setActivityTimeline(prev => [
      ...prev,
      { time: tsNow(), kind: 'action_rejected', action: action.id, message: `Agent rejected: ${action.label}` },
    ])
    sendActionRejected(action.id, callId)
  }, [sendActionRejected, callId])

  /* ── Manual toolkit handler ──────────────────────────────── */
  const fireToolkitAction = useCallback((actionName, extraPayload = {}) => {
    if (!callId) return
    const execId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID() : `exec-${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToolkitStatuses(prev => ({ ...prev, [actionName]: 'running' }))
    setToolkitMessages(prev => ({ ...prev, [actionName]: '' }))
    setToolkitRefs(prev => ({ ...prev, [actionName]: null }))
    sendActionApproved(actionName, extraPayload, execId, callId)
    setActivityTimeline(prev => [
      ...prev,
      { time: tsNow(), kind: 'action_approved', action: actionName, message: `Manual: ${actionName.replace(/_/g, ' ')}` },
    ])
  }, [callId, sendActionApproved])

  /* ── Auth gate ────────────────────────────────────────────── */
  if (!agentInfo) return <LoginPage onLogin={handleLogin} />

  const agentName  = agentInfo.name || 'Agent'
  const agentShort = agentName.split(' ').slice(0, 2).join(' ')
  const statusCfg  = STATUS_CONFIG[agentStatus] || STATUS_CONFIG.active

  /* ── Render ───────────────────────────────────────────────── */
  return (
    <div className="w-full h-screen bg-black text-white flex flex-col font-sans overflow-hidden">

      {/* ══ HEADER ═══════════════════════════════════════════════ */}
      <header className="glass h-14 flex items-center justify-between px-5 md:px-8 shrink-0 z-20">

        {/* Logo */}
        <div className="flex items-center gap-3">
          <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
            <path d="M4 16C4 16 7 24 12 24C17 24 15 8 20 8C25 8 28 16 28 16"
              stroke={Y} strokeWidth="3.5" strokeLinecap="round"/>
          </svg>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold tracking-wider text-white">
              Wavvy<span style={{ color: Y }}>.</span>
            </span>
            <span className="hidden sm:inline t-caps text-white/50 border border-white/[0.1] px-2 py-0.5 rounded-full text-[11px]">
              Agent Console
            </span>
          </div>
        </div>

        {/* Status selector */}
        <div className="flex items-center gap-0.5 border border-white/[0.07] rounded-full p-1">
          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
            <button
              key={key}
              onClick={() => handleStatusChange(key)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-semibold tracking-wide transition-all ${
                agentStatus === key
                  ? 'bg-white/[0.07] text-white'
                  : 'text-white/50 hover:text-white/80'
              }`}
            >
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0 transition-all"
                style={{
                  background: agentStatus === key ? cfg.dot : Wa(0.12),
                  boxShadow:  agentStatus === key ? `0 0 5px ${cfg.glow}` : 'none',
                }}
              />
              {cfg.label}
            </button>
          ))}
        </div>

        {/* Agent info + logout */}
        <div className="flex items-center gap-3">
          {callerState === 'active' && (
            <div className="hidden md:flex items-center gap-1.5" style={{ color: Y }}>
              <Activity size={12} className="animate-pulse" />
              <span className="t-caps text-[11px]" style={{ color: Y }}>Live</span>
            </div>
          )}
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-bold shrink-0"
            style={{ background: Ya(0.08), border: `1px solid ${Ya(0.22)}`, color: Y }}
          >
            {initials(agentName)}
          </div>
          <span className="hidden sm:block text-[13px] text-white/72">{agentShort}</span>
          {/* SIM — single button so React keeps focus across Demo→Next transitions */}
          <div className="hidden sm:flex items-center gap-2">
            {simActive && simStep > 0 && (
              <span className="hidden md:block text-[11px] text-white/40 max-w-[140px] truncate">
                {SIM_STEP_LABELS[simStep]}
              </span>
            )}
            <button
              onClick={simActive ? nextStep : runSimulation}
              disabled={simActive && simStep >= simTotalSteps}
              className="flex items-center gap-1.5 text-[13px] font-semibold px-3 py-1.5 rounded-full transition-all disabled:opacity-40"
              style={{ background: Ya(simActive ? 0.12 : 0.07), border: `1px solid ${Ya(simActive ? 0.35 : 0.18)}`, color: Y }}
              title={simActive ? 'Next step (Space / Enter)' : 'Run interactive demo (Space to advance)'}
            >
              {simActive ? (
                simStep === 0    ? <><ArrowRight size={12} /> Start</>        :
                simStep >= simTotalSteps ? <>✓ Done</>                        :
                                   <><ArrowRight size={12} /> Step {simStep}/{simTotalSteps}</>
              ) : (
                <><Zap size={11} /> Demo</>
              )}
            </button>
            {simActive && (
              <button
                onClick={clearSim}
                className="text-white/30 hover:text-white/60 transition-colors text-[12px] px-1"
                title="Exit demo (Escape)"
              >✕</button>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-[13px] text-white/60 hover:text-white border border-white/[0.12] hover:border-white/35 px-3 py-1.5 rounded-full transition-all"
          >
            <LogOut size={12} />
            <span className="hidden sm:block">Sign out</span>
          </button>
        </div>
      </header>

      {/* ══ MOBILE TABS ══════════════════════════════════════════ */}
      <div className="flex lg:hidden border-b border-white/[0.06] shrink-0 z-10" style={{ background: 'var(--app-bg-mid)' }}>
        {['context','conversation','companion'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2.5 text-center text-[12px] font-semibold uppercase tracking-widest transition-all relative ${
              activeTab === tab ? 'text-white border-b-2 border-brand-yellow' : 'text-white/52 hover:text-white/80'
            }`}
          >
            {tab === 'conversation' ? 'Chat' : tab === 'companion' ? 'AI' : 'Info'}
            {tab === 'conversation' && callerState === 'incoming' && (
              <span className="absolute top-2 right-5 w-1.5 h-1.5 rounded-full call-pulse" style={{ background: Y }} />
            )}
          </button>
        ))}
      </div>

      {/* ══ 3-COLUMN WORKSPACE ═══════════════════════════════════ */}
      <div className="flex-1 flex overflow-hidden relative">


        {/* ══ COLUMN 1 — Context ══════════════════════════════ */}
        <div
          className={`shrink-0 flex flex-col overflow-hidden z-10 ${
            activeTab === 'context' ? 'flex absolute inset-0 z-40 w-full' : 'hidden lg:flex'
          }`}
          style={{ background: 'var(--app-card)', width: leftWidth }}
        >
          {customer ? (
            <div className="p-5 space-y-4 flex-1 flex flex-col min-h-0">

              {/* Customer */}
              <div>
                <p className="section-label mb-3">Customer</p>
                <div className="glass-card p-4 space-y-3">
                  <div>
                    <p className="text-sm font-medium text-white">{customer.name}</p>
                    {customer.email && <p className="text-[13px] text-white/62 mt-0.5">{customer.email}</p>}
                    {customer.phone && <p className="text-[13px] text-white/45 mt-0.5 font-mono">{customer.phone}</p>}
                  </div>
                  {(customer.account_type || customer.account_status) && (
                    <div className="flex flex-wrap gap-1.5">
                      {customer.account_type && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full capitalize"
                          style={{ background: Ya(0.07), color: Y, border: `1px solid ${Ya(0.18)}` }}>
                          {customer.account_type}
                        </span>
                      )}
                      {customer.account_status && customer.account_status !== 'active' && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full capitalize"
                          style={{ background: 'rgba(252,83,91,0.08)', color: '#fc535b', border: '1px solid rgba(252,83,91,0.22)' }}>
                          {customer.account_status}
                        </span>
                      )}
                      {customer.kyc_status && customer.kyc_status !== 'verified' && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full capitalize"
                          style={{ background: 'rgba(250,188,45,0.08)', color: '#fabc2d', border: '1px solid rgba(250,188,45,0.22)' }}>
                          KYC: {customer.kyc_status}
                        </span>
                      )}
                      {customer.fraud_hold && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1"
                          style={{ background: 'rgba(252,83,91,0.10)', color: '#fc535b', border: '1px solid rgba(252,83,91,0.28)' }}>
                          ⚠ Fraud Hold
                        </span>
                      )}
                    </div>
                  )}
                  {customer.intent && (
                    <p className="text-[12px] leading-relaxed" style={{ color: Wa(0.55) }}>
                      <span style={{ color: Wa(0.35) }}>Intent: </span>{customer.intent}
                    </p>
                  )}
                </div>
              </div>

              {/* Sentiment */}
              <div>
                <p className="section-label mb-3">Sentiment</p>
                <div className="glass-card p-4 flex items-center gap-3">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: (callerState === 'active' || callerState === 'incoming') ? (MOOD_COLOR[customerMood] || Wa(0.55)) : Wa(0.18) }}
                  />
                  <span className="text-sm font-medium capitalize"
                    style={{ color: (callerState === 'active' || callerState === 'incoming') ? (MOOD_COLOR[customerMood] || Wa(0.65)) : Wa(0.50) }}>
                    {(callerState === 'active' || callerState === 'incoming') ? customerMood : 'Waiting'}
                  </span>
                </div>
              </div>

              {/* Transfer reason */}
              {handoff?.reason && (
                <div>
                  <p className="section-label mb-3">Transfer Reason</p>
                  <div className="glass-card p-4">
                    <p className="text-[13px] text-white/68 leading-relaxed">{handoff.reason}</p>
                  </div>
                </div>
              )}

              {/* AI history */}
              <div className="flex-1 flex flex-col min-h-0">
                <p className="section-label mb-3">AI Conversation</p>
                <div className="flex-1 overflow-y-auto space-y-3 pr-0.5">
                  {voiceTx.length === 0 ? (
                    <p className="text-[13px] text-white/45 text-center py-4">No AI transcript</p>
                  ) : voiceTx.map((line, i) => (
                    <div key={i} className="space-y-0.5">
                      <span className="t-caps text-[11px]"
                        style={{ color: line.speaker === 'voice_ai' ? Y : Wa(0.55) }}>
                        {line.speaker === 'voice_ai' ? 'Fin' : 'Customer'}
                      </span>
                      <p className="text-[13px] text-white/68 leading-relaxed">{line.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8 text-center">
              <div className="w-10 h-10 rounded-full flex items-center justify-center"
                style={{ background: Wa(0.03), border: `1px solid ${Wa(0.05)}` }}>
                <Phone size={18} className="text-white/38" />
              </div>
              <div>
                <p className="text-[13px] font-medium text-white/55">No active call</p>
                <p className="text-[13px] text-white/40 mt-1 leading-relaxed">Customer context loads automatically</p>
              </div>
            </div>
          )}
        </div>

        {/* ── Left resize handle ──────────────────────────── */}
        <div
          onMouseDown={e => startDrag('left', e)}
          className="hidden lg:flex w-1 shrink-0 z-20 cursor-col-resize select-none items-stretch group"
          style={{ background: 'rgba(255,255,255,0.05)' }}
          title="Drag to resize"
        >
          <div className="w-full transition-colors group-hover:bg-white/20" />
        </div>

        {/* ══ COLUMN 2 — Conversation ═════════════════════════ */}
        <div
          className={`flex-1 flex flex-col overflow-hidden z-10 ${
            activeTab === 'conversation' ? 'flex' : 'hidden lg:flex'
          }`}
          style={{ background: 'var(--app-bg-mid)' }}
        >

          {/* ─ ACTIVE CALL ─ */}
          {callerState === 'active' && (
            <div className="flex-1 flex flex-col overflow-hidden relative min-h-0">

              {/* Transcript scroll area — bottom padding must exceed controls bar height */}
              <div className={`flex-1 overflow-y-auto px-5 md:px-8 py-6 space-y-5 ${quickReplies.length > 0 ? 'pb-56' : 'pb-36'}`}>
                {liveTx.map((line, i) => {
                  if (line.speaker === 'system') {
                    return (
                      <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        className="flex items-center gap-3 justify-center">
                        <div className="h-px flex-1" style={{ background: Wa(0.05) }} />
                        <span className="text-[12px] font-medium px-3 py-1.5 rounded-full flex items-center gap-1.5"
                          style={{ background: Ya(0.07), color: Y, border: `1px solid ${Ya(0.18)}` }}>
                          <ShieldCheck size={11} /> {line.text}
                        </span>
                        <div className="h-px flex-1" style={{ background: Wa(0.05) }} />
                      </motion.div>
                    )
                  }
                  const isAgent = line.speaker === 'agent'
                  return (
                    <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                      className={`flex flex-col ${isAgent ? 'items-end' : 'items-start'}`}>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-[12px] font-semibold uppercase tracking-wider"
                          style={{ color: isAgent ? Y : Wa(0.7) }}>
                          {isAgent ? agentShort : (customer?.name || 'Customer')}
                        </span>
                        <span className="text-[11px] font-mono text-white/42">{line.time}</span>
                      </div>
                      <div
                        className={`max-w-[78%] px-4 py-3 text-[14px] leading-relaxed ${
                          isAgent ? 'rounded-[16px] rounded-tr-[3px]' : 'rounded-[16px] rounded-tl-[3px]'
                        }`}
                        style={isAgent
                          ? { background: Ya(0.07), border: `1px solid ${Ya(0.16)}`, color: '#fff' }
                          : { background: Wa(0.04), border: `1px solid ${Wa(0.07)}`, color: Wa(0.82) }
                        }
                      >
                        {line.text}
                      </div>
                    </motion.div>
                  )
                })}
                <div ref={chatBottom} />
              </div>

              {/* Controls bar — text-to-TTS, no microphone needed */}
              <div
                className="absolute bottom-0 inset-x-0 flex flex-col"
                style={{ background: 'rgba(0,0,0,0.92)', backdropFilter: 'blur(20px)', borderTop: `1px solid ${Wa(0.05)}` }}
              >
                {/* Quick replies from Companion AI */}
                {quickReplies.length > 0 && (
                  <div className="flex flex-wrap gap-2 px-4 pt-3 pb-1">
                    <span className="flex items-center gap-1 t-caps text-[10px] text-white/40 w-full mb-0.5">
                      <Sparkles size={9} style={{ color: Y }} /> Quick replies
                    </span>
                    {quickReplies.map((reply, i) => (
                      <button
                        key={i}
                        onClick={() => sendAgentMessage(reply)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] leading-snug text-left transition-all max-w-full"
                        style={{ background: Ya(0.06), border: `1px solid ${Ya(0.18)}`, color: Wa(0.85) }}
                        onMouseEnter={e => { e.currentTarget.style.background = Ya(0.13); e.currentTarget.style.borderColor = Ya(0.35) }}
                        onMouseLeave={e => { e.currentTarget.style.background = Ya(0.06); e.currentTarget.style.borderColor = Ya(0.18) }}
                      >
                        <MessageSquare size={10} style={{ color: Y, flexShrink: 0 }} />
                        <span className="line-clamp-2">{reply}</span>
                      </button>
                    ))}
                  </div>
                )}
                {/* Text input row */}
                <div className="flex items-center gap-2 px-4 md:px-6 py-2.5">
                  <div
                    className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg"
                    style={{ background: Wa(0.05), border: `1px solid ${Wa(0.18)}` }}
                  >
                    <input
                      ref={chatInputRef}
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && chatInput.trim()) handleChatSend() }}
                      placeholder="Type to speak to customer via Fin AI voice…"
                      className="flex-1 bg-transparent text-[13px] text-white/90 placeholder-white/38 focus:outline-none"
                      style={{ caretColor: Y }}
                    />
                    <button
                      onClick={handleChatSend}
                      disabled={!chatInput.trim()}
                      className="w-6 h-6 rounded-full flex items-center justify-center transition-all disabled:opacity-25 shrink-0"
                      style={{ background: Ya(0.1), border: `1px solid ${Ya(0.25)}`, color: Y }}
                      onMouseEnter={e => { if (chatInput.trim()) e.currentTarget.style.background = Ya(0.2) }}
                      onMouseLeave={e => { e.currentTarget.style.background = Ya(0.1) }}
                    >
                      <Send size={11} />
                    </button>
                  </div>
                </div>
                {/* Status / end call row */}
                <div className="flex items-center justify-between px-5 md:px-8 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full relative" style={{ background: Y, boxShadow: `0 0 6px ${Ya(0.6)}` }}>
                      <span className="absolute inset-0 rounded-full animate-ping" style={{ background: Y, opacity: 0.35 }} />
                    </span>
                    <span className="t-caps text-[11px] text-white/55 hidden sm:block">Live — voice via Fin AI</span>
                  </div>
                  <button
                    onClick={handleEndCall}
                    className="flex items-center gap-2 px-5 py-2 rounded-full text-[13px] font-semibold transition-all"
                    style={{ background: Wa(0.05), border: `1px solid ${Wa(0.14)}`, color: Wa(0.65) }}
                    onMouseEnter={e => { e.currentTarget.style.background = Wa(0.1); e.currentTarget.style.color = '#fff' }}
                    onMouseLeave={e => { e.currentTarget.style.background = Wa(0.05); e.currentTarget.style.color = Wa(0.65) }}
                  >
                    <PhoneOff size={13} />
                    End Call
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ─ ACW ─ */}
          {callerState === 'acw' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="flex-1 overflow-y-auto min-h-0 p-6 md:p-10 space-y-7">
              <div>
                <span className="t-caps text-[11px] mb-3 block" style={{ color: Y }}>After Call Work</span>
                <h2 className="t-h3 text-white">Call Summary</h2>
                <p className="text-sm text-white/58 mt-2">Review, edit, and submit the AI-generated summary.</p>
              </div>

              {acwSubmitted ? (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  className="rounded-[18px] p-8 text-center space-y-4"
                  style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}>
                  <div className="w-12 h-12 rounded-full mx-auto flex items-center justify-center"
                    style={{ background: Ya(0.08), border: `1px solid ${Ya(0.18)}`, color: Y }}>
                    <CheckCircle2 size={22} />
                  </div>
                  <h4 className="text-base font-medium text-white">Submitted</h4>
                  <p className="text-[13px] text-white/58">Summary saved and synced to CRM.</p>
                </motion.div>
              ) : (
                <form onSubmit={handleAcwSubmit} className="space-y-5">
                  <div>
                    <label className="section-label mb-2 block">Resolution</label>
                    <div className="relative">
                      <select
                        value={resolution}
                        onChange={e => setResolution(e.target.value)}
                        className="w-full px-4 py-3 pr-10 rounded-xl text-sm text-white focus:outline-none appearance-none"
                        style={{ background: Wa(0.05), border: `1px solid ${Wa(0.12)}` }}
                      >
                        <option value="resolved">Resolved — Issue addressed on call</option>
                        <option value="escalated">Escalated — Routed to next tier</option>
                        <option value="unresolved">Unresolved — Follow-up required</option>
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 pointer-events-none w-4 h-4" />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="section-label flex items-center gap-1.5">
                        <Sparkles size={9} style={{ color: Y }} /> Summary
                      </label>
                      <button type="button"
                        onClick={() => setSummaryText(acwData?.summary || summaryText)}
                        className="text-[11px] font-mono text-white/45 hover:text-white/75 flex items-center gap-1 transition-colors">
                        <RefreshCw size={8} /> Reset
                      </button>
                    </div>
                    <textarea
                      value={summaryText}
                      onChange={e => setSummaryText(e.target.value)}
                      rows={6}
                      placeholder="Generating summary…"
                      className="w-full px-4 py-3 rounded-xl text-[13px] text-white/80 font-mono leading-relaxed focus:outline-none resize-none"
                      style={{ background: Wa(0.04), border: `1px solid ${Wa(0.10)}` }}
                    />
                  </div>

                  {acwData?.action_items?.length > 0 && (
                    <div>
                      <label className="section-label mb-2 block">Action Items</label>
                      <ul className="space-y-2">
                        {acwData.action_items.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-[13px] text-white/68">
                            <ArrowRight size={11} className="mt-0.5 shrink-0" style={{ color: Y }} />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {acwData?.coaching_note && (
                    <div className="rounded-xl p-4 space-y-1.5"
                      style={{ background: Ya(0.04), border: `1px solid ${Ya(0.12)}` }}>
                      <span className="t-caps text-[11px] flex items-center gap-1.5" style={{ color: Y }}>
                        <Lightbulb size={9} /> Coaching Note
                      </span>
                      <p className="text-[13px] text-white/68 leading-relaxed">{acwData.coaching_note}</p>
                    </div>
                  )}

                  <button type="submit"
                    className="w-full py-3.5 rounded-full text-[13px] font-bold uppercase tracking-widest transition-all"
                    style={{ background: Y, color: '#000', boxShadow: `0 4px 20px ${Ya(0.14)}` }}
                    onMouseEnter={e => e.currentTarget.style.boxShadow = `0 4px 30px ${Ya(0.28)}`}
                    onMouseLeave={e => e.currentTarget.style.boxShadow = `0 4px 20px ${Ya(0.14)}`}
                  >
                    Submit &amp; Close
                  </button>
                </form>
              )}
            </motion.div>
          )}

          {/* ─ INCOMING — HandoffCard fills Column 2 ─ */}
          {callerState === 'incoming' && (
            <HandoffCard
              customer={customer}
              handoff={handoff}
              caseInvestigation={caseInvestigation}
              onAccept={handleAcceptCall}
              onDecline={handleDeclineCall}
            />
          )}

          {/* ─ IDLE ─ */}
          {callerState === 'idle' && (
            <div className="flex-1 flex flex-col items-center justify-center gap-8 p-12 text-center">
              <div className="relative flex items-center justify-center">
                {agentStatus === 'active' && (
                  <div className="absolute w-24 h-24 rounded-full call-pulse-white"
                    style={{ border: `1px solid ${Wa(0.08)}` }} />
                )}
                <div
                  className="relative w-16 h-16 rounded-full flex items-center justify-center"
                  style={{
                    background: Wa(0.025),
                    border: `1px solid ${
                      agentStatus === 'active' ? Ya(0.3) :
                      agentStatus === 'busy'   ? Wa(0.2) :
                                                 Wa(0.07)
                    }`,
                    color: agentStatus === 'active' ? Y : agentStatus === 'busy' ? Wa(0.65) : Wa(0.45),
                  }}
                >
                  <Phone size={24} className={agentStatus === 'active' ? 'animate-pulse' : ''} />
                </div>
              </div>
              <div className="space-y-2">
                {agentStatus === 'active' && (
                  <>
                    <h3 className="t-h3 text-white">Ready for calls</h3>
                    <p className="text-sm text-white/58 max-w-xs mx-auto leading-relaxed">Incoming calls escalated from the Voice AI will appear here automatically.</p>
                  </>
                )}
                {agentStatus === 'busy' && (
                  <>
                    <h3 className="t-h3" style={{ color: Wa(0.5) }}>Busy</h3>
                    <p className="text-sm text-white/58 max-w-xs mx-auto leading-relaxed">New calls won't be routed to you while you're busy.</p>
                  </>
                )}
                {agentStatus === 'inactive' && (
                  <>
                    <h3 className="t-h3 text-white/48">Inactive</h3>
                    <p className="text-sm text-white/48 max-w-xs mx-auto leading-relaxed">Set status to Active to start receiving calls.</p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Right resize handle ─────────────────────────── */}
        <div
          onMouseDown={e => startDrag('right', e)}
          className="hidden lg:flex w-1 shrink-0 z-20 cursor-col-resize select-none items-stretch group"
          style={{ background: 'rgba(255,255,255,0.05)' }}
          title="Drag to resize"
        >
          <div className="w-full transition-colors group-hover:bg-white/20" />
        </div>

        {/* ══ COLUMN 3 — Companion AI (Elite) ═════════════════ */}
        <div
          className={`shrink-0 flex flex-col overflow-hidden z-10 ${
            activeTab === 'companion' ? 'flex absolute inset-0 z-40 w-full' : 'hidden lg:flex'
          }`}
          style={{ background: 'var(--app-card)', width: rightWidth }}
        >
          <div className="p-5 flex-1 flex flex-col gap-4 min-h-0 overflow-y-auto">

            {/* Panel header + tab toggle */}
            <div className="flex items-center justify-center relative">
              <div className="flex items-center gap-1 p-0.5 rounded-lg" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
                {[['companion', 'AI'], ['toolkit', 'Manual']].map(([tab, label]) => (
                  <button key={tab} onClick={() => setRightTab(tab)}
                    className="text-[11px] font-semibold px-3 py-1 rounded-md transition-all"
                    style={rightTab === tab
                      ? { background: Ya(0.10), color: Y, border: `1px solid ${Ya(0.22)}` }
                      : { color: 'rgba(255,255,255,0.40)', border: '1px solid transparent' }}>
                    {label}
                  </button>
                ))}
              </div>
              {/* Sentiment trend arrow */}
              {rightTab === 'companion' && callerState === 'active' && sentimentTrend !== 'stable' && (
                <span className="absolute right-0 text-[11px] font-semibold px-2 py-1 rounded-full"
                  style={{
                    background: sentimentTrend === 'improving' ? 'rgba(29,158,117,0.1)' : 'rgba(252,83,91,0.1)',
                    color: sentimentTrend === 'improving' ? '#1D9E75' : '#fc535b',
                    border: `1px solid ${sentimentTrend === 'improving' ? 'rgba(29,158,117,0.25)' : 'rgba(252,83,91,0.25)'}`,
                  }}>
                  {sentimentTrend === 'improving' ? '↑ Improving' : '↓ Declining'}
                </span>
              )}
            </div>

            {rightTab === 'toolkit' ? (
              /* ══ TOOLKIT PANEL ══════════════════════════════════ */
              <ToolkitPanel
                callId={callId}
                customer={customer}
                toolkitStatuses={toolkitStatuses}
                toolkitMessages={toolkitMessages}
                toolkitRefs={toolkitRefs}
                toolkitParams={toolkitParams}
                setToolkitParams={setToolkitParams}
                toolkitExpanded={toolkitExpanded}
                setToolkitExpanded={setToolkitExpanded}
                fireToolkitAction={fireToolkitAction}
              />
            ) : callerState === 'active' ? (
              <>
                {/* ── 0. CASE INTELLIGENCE ─────────────────────── */}
                <DataAlerts inconsistencies={caseInvestigation?.data_inconsistencies || []} />
                <CaseAnalysis
                  whatHappened={caseInvestigation?.what_happened}
                  knownFacts={caseInvestigation?.known_facts || []}
                  openQuestions={openQuestions}
                />
                <Timeline events={caseInvestigation?.timeline || []} />

                {/* ── 1. OPERATIONAL ACTIONS ──────────────────── */}
                <AnimatePresence>
                  {suggestedActions.filter(a => {
                    const st = actionStatuses[a.id]
                    return !st || st === 'pending' || st === 'executing' || st === 'completed' || st === 'failed'
                  }).map(action => {
                    const status = actionStatuses[action.id] || 'pending'
                    const riskColor = action.risk === 'high' ? '#fc535b' : action.risk === 'low' ? '#1D9E75' : '#fabc2d'
                    const priColor  = action.priority === 'high' ? Y : action.priority === 'low' ? Wa(0.4) : Wa(0.65)
                    return (
                      <motion.div key={action.id}
                        initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.96 }}
                        className="rounded-[14px] p-4 space-y-3"
                        style={{
                          background: status === 'completed' ? 'rgba(29,158,117,0.08)' :
                                      status === 'failed'    ? 'rgba(252,83,91,0.08)'  :
                                      Wa(0.03),
                          border: `1px solid ${
                            status === 'completed' ? 'rgba(29,158,117,0.25)' :
                            status === 'failed'    ? 'rgba(252,83,91,0.25)'  :
                            Wa(0.08)
                          }`,
                        }}>
                        {/* Header row */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-wider"
                              style={{ background: `${priColor}18`, color: priColor, border: `1px solid ${priColor}30` }}>
                              {action.priority}
                            </span>
                            <p className="text-[13px] font-semibold text-white">{action.label}</p>
                          </div>
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full uppercase tracking-wider shrink-0"
                            style={{ background: `${riskColor}15`, color: riskColor, border: `1px solid ${riskColor}28` }}>
                            {action.risk}
                          </span>
                        </div>

                        {/* Why / Impact */}
                        {action.reason && (
                          <div className="space-y-1">
                            <p className="text-[11px] font-semibold text-white/50 uppercase tracking-wider">Why</p>
                            <p className="text-[12px] text-white/70 leading-snug">{action.reason}</p>
                          </div>
                        )}
                        {action.impact && (
                          <div className="space-y-1">
                            <p className="text-[11px] font-semibold text-white/50 uppercase tracking-wider">Impact</p>
                            <p className="text-[12px] text-white/70 leading-snug">{action.impact}</p>
                          </div>
                        )}

                        {/* Confidence */}
                        {action.confidence != null && status === 'pending' && (
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: Wa(0.07) }}>
                              <div className="h-full rounded-full transition-all" style={{
                                width: `${Math.round(action.confidence * 100)}%`,
                                background: action.confidence > 0.7 ? '#1D9E75' : action.confidence > 0.4 ? '#fabc2d' : '#fc535b',
                              }} />
                            </div>
                            <span className="text-[11px] text-white/50 font-mono shrink-0">
                              {Math.round(action.confidence * 100)}% conf
                            </span>
                          </div>
                        )}

                        {/* Status / Buttons */}
                        {status === 'pending' && action.id === 'verify_customer_otp' && (
                          <div className="space-y-2 pt-1">
                            <input
                              type="text"
                              inputMode="numeric"
                              maxLength={6}
                              placeholder="Enter 6-digit OTP"
                              value={otpInputs[action.id] || ''}
                              onChange={e => setOtpInputs(p => ({ ...p, [action.id]: e.target.value.replace(/\D/g, '').slice(0, 6) }))}
                              className="w-full px-3 py-2 rounded-xl text-[13px] font-mono tracking-[0.25em] text-center"
                              style={{ background: Wa(0.06), border: `1px solid ${Wa(0.15)}`, color: '#fff', outline: 'none' }}
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => {
                                  const code = otpInputs[action.id] || ''
                                  if (code.length !== 6) return
                                  handleApproveAction({ ...action, payload: { ...(action.payload || {}), otp_code: code } })
                                }}
                                disabled={!otpInputs[action.id] || otpInputs[action.id].length !== 6}
                                className="flex-1 py-2 rounded-full text-[12px] font-bold uppercase tracking-wider transition-all disabled:opacity-40"
                                style={{ background: Y, color: '#000' }}
                              >
                                ✓ Verify OTP
                              </button>
                              <button onClick={() => handleRejectAction(action)}
                                className="py-2 px-4 rounded-full text-[12px] font-semibold uppercase tracking-wider"
                                style={{ background: Wa(0.04), border: `1px solid ${Wa(0.1)}`, color: Wa(0.5) }}>
                                ✕
                              </button>
                            </div>
                          </div>
                        )}
                        {status === 'pending' && action.id === 'update_account_info' && (
                          <div className="space-y-2 pt-1">
                            <select
                              value={acctUpdateInputs[action.id]?.field || action.payload?.field || ''}
                              onChange={e => setAcctUpdateInputs(p => ({ ...p, [action.id]: { ...(p[action.id] || {}), field: e.target.value } }))}
                              className="w-full px-3 py-2 rounded-xl text-[12px]"
                              style={{ background: Wa(0.06), border: `1px solid ${Wa(0.15)}`, color: '#fff', outline: 'none' }}
                            >
                              <option value="">Select field…</option>
                              <option value="email">Email</option>
                              <option value="name">Name</option>
                            </select>
                            <input
                              type="text"
                              placeholder="New value"
                              value={acctUpdateInputs[action.id]?.value || action.payload?.value || ''}
                              onChange={e => setAcctUpdateInputs(p => ({ ...p, [action.id]: { ...(p[action.id] || {}), value: e.target.value } }))}
                              className="w-full px-3 py-2 rounded-xl text-[12px]"
                              style={{ background: Wa(0.06), border: `1px solid ${Wa(0.15)}`, color: '#fff', outline: 'none' }}
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => {
                                  const f = acctUpdateInputs[action.id]?.field || action.payload?.field
                                  const v = acctUpdateInputs[action.id]?.value || action.payload?.value
                                  if (!f || !v) return
                                  handleApproveAction({ ...action, payload: { ...(action.payload || {}), field: f, value: v } })
                                }}
                                disabled={!(acctUpdateInputs[action.id]?.field || action.payload?.field) || !(acctUpdateInputs[action.id]?.value || action.payload?.value)}
                                className="flex-1 py-2 rounded-full text-[12px] font-bold uppercase tracking-wider transition-all disabled:opacity-40"
                                style={{ background: Y, color: '#000' }}
                              >
                                ✓ Update
                              </button>
                              <button onClick={() => handleRejectAction(action)}
                                className="py-2 px-4 rounded-full text-[12px] font-semibold uppercase tracking-wider"
                                style={{ background: Wa(0.04), border: `1px solid ${Wa(0.1)}`, color: Wa(0.5) }}>
                                ✕
                              </button>
                            </div>
                          </div>
                        )}
                        {status === 'pending' && action.id !== 'verify_customer_otp' && action.id !== 'update_account_info' && (
                          <div className="flex gap-2 pt-1">
                            <button
                              onClick={() => handleApproveAction(action)}
                              className="flex-1 py-2 rounded-full text-[12px] font-bold uppercase tracking-wider transition-all"
                              style={{ background: Y, color: '#000' }}
                              onMouseEnter={e => { e.currentTarget.style.boxShadow = `0 0 14px ${Ya(0.3)}` }}
                              onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none' }}
                            >
                              ✓ Approve
                            </button>
                            <button
                              onClick={() => handleRejectAction(action)}
                              className="flex-1 py-2 rounded-full text-[12px] font-semibold uppercase tracking-wider transition-all"
                              style={{ background: Wa(0.04), border: `1px solid ${Wa(0.1)}`, color: Wa(0.5) }}
                              onMouseEnter={e => { e.currentTarget.style.color = Wa(0.8) }}
                              onMouseLeave={e => { e.currentTarget.style.color = Wa(0.5) }}
                            >
                              ✕ Reject
                            </button>
                          </div>
                        )}
                        {status === 'executing' && (
                          <div className="flex items-center gap-2 py-1">
                            <div className="w-3 h-3 rounded-full border-2 border-transparent animate-spin shrink-0"
                              style={{ borderTopColor: Y }} />
                            <span className="text-[12px] text-white/55">Executing…</span>
                          </div>
                        )}
                        {status === 'completed' && (
                          <div className="flex items-center gap-2 py-1">
                            <CheckCircle2 size={14} style={{ color: '#1D9E75' }} />
                            <span className="text-[12px]" style={{ color: '#1D9E75' }}>Completed</span>
                          </div>
                        )}
                        {status === 'failed' && (
                          <div className="flex items-center gap-2 py-1">
                            <AlertCircle size={14} style={{ color: '#fc535b' }} />
                            <span className="text-[12px]" style={{ color: '#fc535b' }}>Failed — check state</span>
                          </div>
                        )}
                      </motion.div>
                    )
                  })}
                </AnimatePresence>

                {/* ── 2. MOOD ARC ─────────────────────────────── */}
                {sentimentHistory.length > 0 && (
                  <div className="space-y-2">
                    <p className="section-label flex items-center gap-1.5">
                      <Activity size={9} /> Sentiment Arc
                    </p>
                    <div className="flex items-center gap-1.5">
                      {sentimentHistory.map((h, i) => {
                        const c = h.mood === 'satisfied' ? '#1D9E75' :
                                  h.mood === 'curious'   ? Y :
                                  h.mood === 'calm'      ? Wa(0.4) :
                                  h.mood === 'frustrated'? '#fabc2d' : '#fc535b'
                        return (
                          <div key={i}
                            className="w-2.5 h-2.5 rounded-full shrink-0 transition-all"
                            style={{ background: c, opacity: 0.5 + (i / sentimentHistory.length) * 0.5 }}
                            title={h.mood}
                          />
                        )
                      })}
                      <span className="text-[11px] text-white/45 ml-1 capitalize">{customerMood}</span>
                    </div>
                  </div>
                )}


                {/* ── 4. RISK FLAGS ───────────────────────────── */}
                {riskFlags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {riskFlags.map(flag => (
                      <span key={flag} className="text-[11px] font-semibold px-2 py-1 rounded-full flex items-center gap-1"
                        style={{ background: 'rgba(250,188,45,0.08)', color: '#fabc2d', border: '1px solid rgba(250,188,45,0.2)' }}>
                        <AlertCircle size={8} />
                        {flag.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </span>
                    ))}
                  </div>
                )}

                {/* ── 5. NEXT ACTION ──────────────────────────── */}
                {nextAction && (
                  <div className="rounded-[14px] p-4 space-y-1.5"
                    style={{ background: Ya(0.04), border: `1px solid ${Ya(0.14)}` }}>
                    <span className="t-caps text-[11px] flex items-center gap-1.5" style={{ color: Y }}>
                      <Zap size={8} /> Next Step
                    </span>
                    <p className="text-[13px] text-white/85 leading-snug">{nextAction}</p>
                  </div>
                )}

                {/* ── 6. NUDGE ────────────────────────────────── */}
                <AnimatePresence>
                  {nudge && (
                    <motion.div key={nudge}
                      initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }}
                      className="rounded-[14px] p-4 space-y-1.5 cursor-pointer group"
                      style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
                      onClick={() => { setChatInput(nudge); setTimeout(() => chatInputRef.current?.focus(), 0) }}
                      title="Click to paste into message input"
                    >
                      <span className="t-caps text-[11px] flex items-center justify-between gap-1.5 text-white/55">
                        <span className="flex items-center gap-1.5"><AlertCircle size={8} /> Nudge</span>
                        <span className="text-[10px] text-white/30 group-hover:text-white/55 transition-colors">click to paste ↗</span>
                      </span>
                      <p className="text-[13px] text-white/75 leading-relaxed group-hover:text-white/90 transition-colors">{nudge}</p>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* ── 7. KB SUGGESTION ────────────────────────── */}
                <AnimatePresence>
                  {kbSuggestion && (
                    <motion.div key="kb"
                      initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
                      className="rounded-[14px] p-4 space-y-2"
                      style={{ background: Wa(0.03), border: `1px solid ${Wa(0.08)}` }}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="t-caps text-[11px] flex items-center gap-1.5" style={{ color: Y }}>
                          <BookOpen size={8} /> KB Match
                        </span>
                        <span className="text-[11px] font-mono text-white/48 truncate">{kbSuggestion.source}</span>
                      </div>
                      <p className="text-[13px] text-white/75 leading-relaxed">{kbSuggestion.content}</p>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* ── 8. CHECKLIST ────────────────────────────── */}
                {checklist.length > 0 && (
                  <div className="space-y-2 border-t border-white/[0.05] pt-4">
                    <div className="flex items-center justify-between">
                      <p className="section-label">Checklist</p>
                      <span className="text-[11px] font-mono text-white/48">
                        {checklist.filter(c => c.done).length}/{checklist.length}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {checklist.map((item, idx) => (
                        <button key={idx} onClick={() => toggleChecklistItem(idx)}
                          className={`w-full flex items-start gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all ${item.done ? 'opacity-35' : 'hover:bg-white/[0.025]'}`}>
                          <div className="mt-0.5 w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 transition-all"
                            style={item.done
                              ? { background: Y, border: `1px solid ${Y}` }
                              : { border: `1px solid ${Wa(0.18)}` }
                            }>
                            {item.done && <CheckCheck size={9} style={{ color: '#000' }} strokeWidth={3} />}
                          </div>
                          <span className={`text-[13px] leading-snug ${item.done ? 'line-through text-white/35' : 'text-white/78'}`}>
                            {item.step}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── 9. INSIGHT ──────────────────────────────── */}
                {insight && (
                  <div className="rounded-[12px] p-3 space-y-1"
                    style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}>
                    <span className="t-caps text-[11px] flex items-center gap-1 text-white/50">
                      <Lightbulb size={8} /> Insight
                    </span>
                    <p className="text-[12px] text-white/65 leading-relaxed italic">{insight}</p>
                  </div>
                )}

                {/* ── 10. ACW PREVIEW (collapsible) ───────────── */}
                {acwPreview?.summary && (
                  <div className="border-t border-white/[0.05] pt-3">
                    <button
                      onClick={() => setAcwPreviewOpen(v => !v)}
                      className="w-full flex items-center justify-between text-left"
                    >
                      <span className="section-label flex items-center gap-1.5">
                        <CheckCheck size={9} /> ACW Preview
                      </span>
                      <ChevronDown size={12} className={`text-white/40 transition-transform ${acwPreviewOpen ? 'rotate-180' : ''}`} />
                    </button>
                    <AnimatePresence>
                      {acwPreviewOpen && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                          className="overflow-hidden mt-2 space-y-2"
                        >
                          <p className="text-[12px] text-white/68 leading-relaxed">{acwPreview.summary}</p>
                          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                            style={{
                              background: acwPreview.likely_resolution === 'resolved' ? 'rgba(29,158,117,0.1)' :
                                          acwPreview.likely_resolution === 'escalated'? 'rgba(250,188,45,0.08)' :
                                          Wa(0.04),
                              color: acwPreview.likely_resolution === 'resolved' ? '#1D9E75' :
                                     acwPreview.likely_resolution === 'escalated' ? '#fabc2d' : Wa(0.55),
                            }}>
                            Likely: {acwPreview.likely_resolution}
                          </span>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}

                {/* ── 11. ACTIVITY TIMELINE (collapsible) ─────── */}
                {activityTimeline.length > 0 && (
                  <div className="border-t border-white/[0.05] pt-3">
                    <button
                      onClick={() => setTimelineOpen(v => !v)}
                      className="w-full flex items-center justify-between text-left"
                    >
                      <span className="section-label flex items-center gap-1.5">
                        <Activity size={9} /> Activity
                        <span className="ml-1 text-[10px] font-mono text-white/40">({activityTimeline.length})</span>
                      </span>
                      <ChevronDown size={12} className={`text-white/40 transition-transform ${timelineOpen ? 'rotate-180' : ''}`} />
                    </button>
                    <AnimatePresence>
                      {timelineOpen && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                          className="overflow-hidden mt-3 space-y-2.5 max-h-[220px] overflow-y-auto"
                        >
                          {activityTimeline.map((ev, i) => {
                            const icon = ev.kind === 'action_executed' ? <Zap size={9} /> :
                                         ev.kind === 'action_approved' ? <CheckCircle2 size={9} /> :
                                         ev.kind === 'action_rejected' ? <AlertCircle size={9} /> :
                                         <Sparkles size={9} />
                            const color = ev.kind === 'action_executed' ? '#1D9E75' :
                                          ev.kind === 'action_approved' ? Y :
                                          ev.kind === 'action_rejected' ? Wa(0.35) :
                                          Wa(0.5)
                            return (
                              <div key={i} className="flex items-start gap-2">
                                <span className="mt-0.5 shrink-0" style={{ color }}>{icon}</span>
                                <div>
                                  <p className="text-[11px] text-white/65 leading-snug">{ev.message}</p>
                                  {ev.reference_numbers && (
                                    <p className="text-[10px] font-mono mt-0.5" style={{ color: '#f4f73d', letterSpacing: '0.04em' }}>
                                      {Object.values(ev.reference_numbers).join(' · ')}
                                    </p>
                                  )}
                                  <p className="text-[10px] font-mono text-white/35 mt-0.5">{ev.time}</p>
                                </div>
                              </div>
                            )
                          })}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center py-8">
                <Sparkles size={20} className="text-white/25" />
                <div>
                  <p className="text-[13px] text-white/55 font-medium">Operational co-pilot ready</p>
                  <p className="text-[13px] text-white/42 mt-1 leading-relaxed max-w-[160px] mx-auto">Actions, nudges, KB matches and audit trail appear here during live calls</p>
                </div>
              </div>
            )}
          </div>
          <LiveDocumentation liveDoc={liveDoc} />
        </div>

      </div>

      {/* ══ STATUS BAR ══════════════════════════════════════════ */}
      <div
        className="h-8 flex items-center justify-between px-5 shrink-0 z-[2]"
        style={{ background: 'rgba(0,0,0,0.75)', borderTop: `1px solid ${Wa(0.04)}` }}
      >
        <span className="t-caps text-[11px] text-white/48">
          {callerState === 'active' ? 'Call in progress' : callerState === 'acw' ? 'After call work' : 'Ready'}
        </span>
        <div className="flex items-center gap-2">
          {callerState === 'active' && customer?.name && (
            <span className="t-caps text-[11px] text-white/48">{customer.name}</span>
          )}
          {callerState !== 'active' && (
            <span className="t-caps text-[11px]" style={{ color: statusCfg.dot }}>{statusCfg.label}</span>
          )}
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background:  callerState === 'active' ? Y : statusCfg.dot,
              boxShadow:   callerState === 'active' ? `0 0 4px ${Ya(0.6)}` : `0 0 4px ${statusCfg.glow}`,
            }}
          />
        </div>
      </div>
    </div>
  )
}
