/**
 * SIMULATION MODULE — delete this file and its 3 references in App.jsx to remove.
 * Search for "// SIM" in App.jsx to find every reference.
 *
 * Scenario: Kavya Reddy — stale fraud hold after case cleared (authority escalation).
 * 11 interactive steps, each triggered by Space / Enter.
 * Showcases every console feature end-to-end.
 *
 * Step 0   Ready                  — demo mode entered, waiting for first ⎵
 * Step 1   Incoming Call          — HandoffCard appears, case analysis loading
 * Step 2   Investigation Complete — HandoffCard populates: risk, alerts, facts, questions, timeline
 * Step 3   Call Accepted          — agent answers, transcript starts, companion fires
 * Step 4   Customer Asks Q        — nudge = direct answer to ref-number question; quick replies
 * Step 5   Companion Analyzes     — risk flags, 30% resolution, Remove Fraud Hold action; agent peeks Manual tab
 * Step 6   Customer Asks Docs     — nudge answers "no documents needed"; agent back on Companion tab
 * Step 7   Fraud Hold Lifted      — agent approves companion action → executing → completed; live doc updates
 * Step 8   Agent → Manual Tab     — companion re-fires with Unlock Account; agent switches to Manual tab
 * Step 9   Account Unlocked (Manual) — agent fires Unlock Account via Manual Toolkit; toolkit status → ok
 * Step 10  Issue Resolved         — checklist done, satisfied mood, 93% resolution
 * Step 11  ACW Generated          — instant from live documentation
 */
import { useRef, useState, useCallback } from 'react'

function ts() { return new Date().toTimeString().split(' ')[0] }

export const SIM_TOTAL_STEPS = 11

export const SIM_STEP_LABELS = {
  0:  'Ready',
  1:  'Incoming Call',
  2:  'Case Investigation Done',
  3:  'Call Accepted',
  4:  'Customer Asks: Ref No',
  5:  'Companion Analyzes',
  6:  'Customer Asks: Documents',
  7:  'Fraud Hold Lifted (Companion)',
  8:  'Agent → Manual Tab',
  9:  'Account Unlocked (Manual)',
  10: 'Issue Resolved',
  11: 'ACW Generated',
}

/* ── Customer & handoff ─────────────────────────────────────────── */

const DEMO_CUSTOMER = {
  name:           'Kavya Reddy',
  email:          'kavya.reddy@email.com',
  phone:          '+91 87654 32109',
  account_type:   'premium',
  account_status: 'locked',
  kyc_status:     'verified',
  fraud_hold:     true,
  intent:         'account access',
}

const DEMO_HANDOFF = {
  reason:      'Account locked + fraud hold active since 24 May. Fraud review team cleared case FC-0291 on 25 May at 09:14 but system hold was never lifted (sync delay). Customer called yesterday (INC-4412) without resolution.',
  customer_id: 'CUST-demo-001',
}

const DEMO_VOICE_TX = [
  { speaker: 'voice_ai', text: 'Hi, this is Fin. How can I help you today?',                              time: '10:41:03' },
  { speaker: 'customer', text: 'My account is completely locked. My card is being declined everywhere.',   time: '10:41:09' },
  { speaker: 'voice_ai', text: 'I\'m sorry to hear that. Let me pull up your account.',                   time: '10:41:13' },
  { speaker: 'customer', text: 'My phone number is +91 87654 32109.',                                     time: '10:41:18' },
  { speaker: 'voice_ai', text: 'Thank you Kavya. Your account is locked due to a fraud hold from 24 May — the fraud team actually cleared your case yesterday but the hold is still active. I need to connect you with a specialist who can lift it immediately.', time: '10:41:26' },
  { speaker: 'customer', text: 'I called yesterday too and nothing changed! This is the second time.',    time: '10:41:35' },
  { speaker: 'voice_ai', text: 'I understand, and I\'m sorry. Escalating you to a senior specialist right now.', time: '10:41:41' },
]

/* ── Case Investigation data ────────────────────────────────────── */

// Step 1: Partial — "Analysing case…" skeleton shown in HandoffCard
const DEMO_CASE_LOADING = {
  case_status:      'investigating',
  escalation_type:  'authority',
  risk:             'HIGH',
  data_inconsistencies: [],
  known_facts:      [],
  open_questions:   [],
  timeline:         [],
  what_happened:    null,
}

// Step 2: Complete — full HandoffCard populates
const DEMO_CASE_COMPLETE = {
  case_status:     'investigation_complete',
  escalation_type: 'authority',
  risk:            'HIGH',

  what_happened:
    'Kavya\'s account was locked on 24 May after an automated fraud alert. The fraud review team cleared the case (FC-0291) on 25 May at 09:14, but the system hold was never lifted due to a sync delay between the fraud review platform and the card system. Customer called yesterday (INC-4412) and was not resolved. This is her second contact for the same issue.',

  known_facts: [
    { fact: 'Identity verified via OTP during AI call',           source: 'AI workflow' },
    { fact: 'Account status: LOCKED since 24 May 2026',          source: 'account profile' },
    { fact: 'Fraud case FC-0291 status: CLEARED at 09:14, 25 May', source: 'fraud case table' },
    { fact: 'Fraud hold still active — sync delay artifact',     source: 'account_holds table' },
    { fact: 'Previous contact INC-4412 yesterday — unresolved',  source: 'call history' },
  ],

  open_questions: [
    {
      question: 'Did customer receive an SMS/email when the hold was supposed to be lifted?',
      why: 'If notification was sent but hold remains, confirms sync failure rather than active review',
    },
    {
      question: 'Is the salary credit visible in the account despite the lock?',
      why: 'Determines urgency — salary may be trapped in the locked account',
    },
  ],

  data_inconsistencies: [
    {
      severity: 'HIGH',
      type:     'orphaned_fraud_hold',
      headline: 'Fraud hold active but case FC-0291 is CLEARED',
      detail:   'Fraud review marked CLEARED on 25 May 09:14. Hold was never lifted — stale system artifact. No active fraud risk. Safe to remove immediately without additional approval.',
      evidence: { fraud_case: 'FC-0291', case_status: 'cleared', hold_active: true },
    },
  ],

  timeline: [
    { ts: '24 May, 11:42', event: 'Fraud alert triggered — account locked automatically' },
    { ts: '24 May, 11:43', event: 'Fraud hold placed — card and UPI blocked' },
    { ts: '24 May, 14:00', event: 'Fraud review opened — case FC-0291' },
    { ts: '25 May, 09:14', event: 'Case FC-0291 CLEARED by fraud review team ✓' },
    { ts: '25 May, ~09:15', event: 'Hold removal FAILED — sync delay between systems' },
    { ts: 'Yesterday',     event: 'Customer called (INC-4412) — specialist unable to resolve' },
    { ts: 'Today 10:41',   event: 'Customer called — AI verified identity via OTP' },
    { ts: 'Today 10:41',   event: 'Escalated: authority escalation (hold removal needs specialist)' },
  ],

  recommended_resolution:
    'Remove fraud hold immediately (FC-0291 cleared — no approval needed). Then unlock account as a separate step. Provide resolution reference. Flag sync delay to engineering.',
}

/* ── Live documentation building up ────────────────────────────── */

const LIVE_DOC_INITIAL = {
  summary:      'Kavya Reddy — stale fraud hold from 24 May. Fraud case FC-0291 cleared on 25 May 09:14, hold never lifted due to sync delay. Second contact (INC-4412 unresolved yesterday).',
  action_items: [],
  crm_fields:   { notes: 'Stale fraud hold — fraud review cleared FC-0291. Sync delay between fraud review and card systems.' },
}

const LIVE_DOC_POST_HOLD = {
  summary:      'Fraud hold (FC-0291) removed manually by specialist. Account lock still active — requires separate unlock action.',
  action_items: ['✓ Fraud hold removed — FC-0291 (25 May clearance confirmed)'],
  crm_fields:   { notes: 'Fraud hold removed. Unlocking account next. Engineering sync delay flag needed.' },
}

const LIVE_DOC_FINAL = {
  summary:      'Both fraud hold and account lock fully lifted. Customer confirmed card working immediately. Resolution reference RES-2026-0522.',
  action_items: [
    '✓ Fraud hold removed — FC-0291',
    '✓ Account unlocked — full access restored',
    'Engineering: investigate fraud-hold sync delay (INC-4412 history shows repeat occurrence)',
  ],
  crm_fields:   { notes: 'Resolved. Stale hold lifted. Customer confirmed access restored. Ref RES-2026-0522.' },
}

/* ── Transcript lines ───────────────────────────────────────────── */

const TX_STEP3 = [
  { speaker: 'customer', text: 'Hello? Is someone there? I\'ve been trying to fix this for two days.' },
  { speaker: 'agent',    text: 'Hi Kavya — I\'m here. I can see your full case including the fraud clearance note from yesterday at 09:14. The hold should have come off automatically. I\'m fixing this right now.' },
  { speaker: 'customer', text: 'Thank goodness. My salary came in yesterday and I literally cannot withdraw anything.' },
]

const TX_STEP4 = [
  { speaker: 'customer', text: 'Can you give me the reference number for my case yesterday? My previous complaint?' },
]

const TX_STEP5_AGENT = 'Your previous contact reference is INC-4412 raised yesterday. Your fraud case reference is FC-0291 — that\'s the one the fraud team cleared on the 25th at 09:14.'

const TX_STEP6 = [
  { speaker: 'agent',    text: TX_STEP5_AGENT },
  { speaker: 'customer', text: 'Okay. And do I need to provide any documents or ID again for this?' },
]

const TX_STEP7_START = [
  { speaker: 'agent', text: 'No documents required at all — the fraud team already completed the review and cleared your case. This is purely a system delay on our side. I\'m removing the hold right now.' },
  { speaker: 'customer', text: 'Okay. How long does this actually take?' },
]

const TX_STEP8 = [
  { speaker: 'agent',    text: 'The hold is off. I\'m now unlocking your account — that\'s a separate step. Should be live within 60 seconds.' },
]

const TX_STEP9 = [
  { speaker: 'customer', text: 'Oh! My card just worked! I literally just got a transaction success notification!' },
  { speaker: 'agent',    text: 'Both the fraud hold and account lock are fully lifted. Your resolution reference is RES-2026-0522. I\'ve flagged the sync delay to our engineering team so this doesn\'t happen again.' },
]

const TX_STEP10 = [
  { speaker: 'customer', text: 'Thank you so much. I was so stressed about this. Really appreciate it.' },
  { speaker: 'agent',    text: 'You\'re very welcome, Kavya. I\'m sorry this took two contacts — that shouldn\'t happen. Take care!' },
]

/* ── Companion payloads ─────────────────────────────────────────── */

const CHECKLIST_INITIAL = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: false },
  { step: 'Confirm fraud clearance note (FC-0291, 25 May 09:14)', done: false },
  { step: 'Remove fraud hold via Operational Actions',            done: false },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_STEP3 = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true  },
  { step: 'Confirm fraud clearance note (FC-0291, 25 May 09:14)', done: false },
  { step: 'Remove fraud hold via Operational Actions',            done: false },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_STEP5 = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true  },
  { step: 'Confirm fraud clearance note (FC-0291, 25 May 09:14)', done: true  },
  { step: 'Remove fraud hold via Operational Actions',            done: false },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_STEP8 = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true  },
  { step: 'Confirm fraud clearance note (FC-0291, 25 May 09:14)', done: true  },
  { step: 'Remove fraud hold via Operational Actions',            done: true  },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_DONE = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true  },
  { step: 'Confirm fraud clearance note (FC-0291, 25 May 09:14)', done: true  },
  { step: 'Remove fraud hold via Operational Actions',            done: true  },
  { step: 'Unlock account once hold is lifted',                   done: true  },
  { step: 'Confirm card working and give resolution reference',   done: true  },
]

const ACTION_REMOVE_FRAUD_HOLD = {
  id:               'remove_fraud_hold',
  label:            'Remove Fraud Hold — FC-0291',
  description:      'Lift the stale system hold placed 24 May 2026 (fraud case already cleared)',
  reason:           'Fraud case FC-0291 marked CLEARED by fraud team on 25 May 09:14. Hold is a stale sync artifact — no active fraud risk. Safe to remove without additional approval.',
  impact:           'Unblocks card transactions immediately. Required before account can be unlocked.',
  confidence:       0.92,
  priority:         'high',
  risk:             'low',
  requires_approval: true,
  payload:          { customer_id: 'CUST-demo-001' },
}

const ACTION_UNLOCK_ACCOUNT = {
  id:               'unlock_account',
  label:            'Unlock Account',
  description:      'Restore full account access after fraud clearance and hold removal',
  reason:           'Fraud hold successfully removed. Account lock can now be safely lifted — no remaining restrictions on the account.',
  impact:           'Customer regains full access: card, UPI, and transfers all enabled immediately.',
  confidence:       0.95,
  priority:         'high',
  risk:             'low',
  requires_approval: true,
  payload:          { customer_id: 'CUST-demo-001' },
}

const KB_FRAUD_OPS = {
  source:  'fraud_escalation.md',
  content: 'Fraud hold removal: once the fraud review team marks a case CLEARED, the account specialist may remove the hold immediately without additional approval. Effect is immediate (≤60 seconds). Account unlock must follow as a separate step after hold removal is confirmed.',
}

const DEMO_ACW = {
  summary:
    'Kavya Reddy called regarding a fraud hold that persisted after the fraud team cleared her case (FC-0291) on 25 May 09:14. ' +
    'Specialist confirmed the clearance note, removed the fraud hold, and unlocked the account via Operational Actions. ' +
    'Customer confirmed card working immediately after. This was her second contact for the same issue — INC-4412 went unresolved due to a system sync delay. ' +
    'Resolution reference: RES-2026-0522.',
  resolution:   'resolved',
  action_items: [
    'Engineering: investigate fraud-hold sync delay between fraud review and card system',
    'Flag INC-4412 as resolved — reference RES-2026-0522',
    'Send resolution confirmation SMS to Kavya Reddy (+91 87654 32109)',
  ],
  coaching_note:
    'Strong ownership of a repeat escalation — acknowledged prior contact immediately and provided clear timeline. ' +
    'Good practice: give the resolution reference proactively before the customer asks.',
  crm_fields: {
    issue_type:     'fraud_account_hold',
    resolution_ref: 'RES-2026-0522',
    notes:          'Stale fraud hold (FC-0291) lifted manually. Engineering flagged for sync delay investigation.',
  },
}

/* ── Hook ───────────────────────────────────────────────────────── */

export function useSimulation({
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
}) {
  const timers     = useRef([])
  const stepRef    = useRef(-1)
  const [simStep,  setSimStep]  = useState(-1)

  function after(ms, fn) {
    const id = setTimeout(fn, ms)
    timers.current.push(id)
  }

  function addTx(lines, baseMs = 0) {
    lines.forEach((line, i) => {
      after(baseMs + i * 950, () =>
        setLiveTx(prev => [...prev, { ...line, time: ts() }])
      )
    })
  }

  function addEvent(kind, action, message) {
    setActivityTimeline(prev => [...prev, { time: ts(), kind, action, message }])
  }

  function pushMood(mood) {
    setCustomerMood(mood)
    setSentimentHistory(prev => [...prev.slice(-9), { mood }])
  }

  const doReset = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setCallerState('idle');  setCallId(null)
    setCustomer(null);       setHandoff(null);   setVoiceTx([]);  setLiveTx([])
    setQuickReplies([])
    setChecklist([]);        setNudge(null);     setNextAction(''); setCustomerMood('calm')
    setKbSuggestion(null);  setInsight(null)
    setAcwData(null);       setSummaryText(''); setResolution('resolved'); setAcwSubmitted(false)
    setSuggestedActions([]);  setActionStatuses({});  setActivityTimeline([])
    setSentimentHistory([]);  setResolutionProb(null); setSentimentTrend('stable')
    setRiskFlags([]);         setAcwPreview(null)
    setCaseInvestigation(null); setOpenQuestions([]); setLiveDoc(null)
    if (setRightTab)        setRightTab('companion')
    if (setToolkitStatuses) setToolkitStatuses({})
    if (setToolkitMessages) setToolkitMessages({})
    if (setToolkitRefs)     setToolkitRefs({})
  }, [
    setCallerState, setCallId, setCustomer, setHandoff, setVoiceTx, setLiveTx,
    setQuickReplies,
    setChecklist, setNudge, setNextAction, setCustomerMood, setKbSuggestion, setInsight,
    setAcwData, setSummaryText, setResolution, setAcwSubmitted,
    setSuggestedActions, setActionStatuses, setActivityTimeline, setSentimentHistory,
    setResolutionProb, setSentimentTrend, setRiskFlags, setAcwPreview,
    setCaseInvestigation, setOpenQuestions, setLiveDoc,
    setRightTab, setToolkitStatuses, setToolkitMessages, setToolkitRefs,
  ])

  const runSimulation = useCallback(() => {
    doReset()
    stepRef.current = 0
    setSimStep(0)
  }, [doReset])

  const clearSim = useCallback(() => {
    doReset()
    stepRef.current = -1
    setSimStep(-1)
  }, [doReset])

  const nextStep = useCallback(() => {
    if (stepRef.current < 0) return
    if (stepRef.current >= SIM_TOTAL_STEPS) return

    timers.current.forEach(clearTimeout)
    timers.current = []

    const step = stepRef.current + 1
    stepRef.current = step
    setSimStep(step)

    switch (step) {

      /* ── 1: Incoming call rings — HandoffCard with "Analysing case…" ── */
      case 1:
        setCallId('demo-call-001')
        setCustomer(DEMO_CUSTOMER)
        setHandoff(DEMO_HANDOFF)
        setVoiceTx(DEMO_VOICE_TX)
        setChecklist(CHECKLIST_INITIAL)
        // Case investigation starts but isn't complete yet — shows skeleton
        setCaseInvestigation(DEMO_CASE_LOADING)
        setOpenQuestions([])
        setLiveDoc(null)
        setCallerState('incoming')
        break

      /* ── 2: Case investigation complete — HandoffCard fully populated ── */
      case 2:
        setCaseInvestigation(DEMO_CASE_COMPLETE)
        setOpenQuestions(DEMO_CASE_COMPLETE.open_questions)
        setLiveDoc(LIVE_DOC_INITIAL)
        break

      /* ── 3: Agent accepts — active call, customer speaks, companion fires ── */
      case 3:
        setLiveTx([{ speaker: 'system', text: 'Call connected — Kavya Reddy is on the line.', time: ts() }])
        setCallerState('active')
        addTx(TX_STEP3, 600)
        pushMood('frustrated')
        setSentimentHistory([{ mood: 'frustrated' }, { mood: 'frustrated' }])
        setSentimentTrend('stable')
        after(900, () => {
          setChecklist(CHECKLIST_STEP3)
          setNextAction('Confirm you can see the fraud clearance note (FC-0291, cleared 25 May 09:14) before taking action')
          setQuickReplies([
            'I can see your full case — fraud team cleared FC-0291 yesterday at 09:14, the hold is a system delay on our end.',
            'I can see this is your second contact about the same issue. I\'m resolving this right now.',
            'I can confirm the fraud team cleared your case. The hold should have lifted automatically — it didn\'t. I\'m fixing it.',
          ])
          setInsight('Salary likely trapped in locked account — customer mentioned it arrived yesterday. Prioritise speed.')
          setRiskFlags(['repeat_complaint', 'unresolved_ai_attempt'])
        })
        break

      /* ── 4: Customer asks for reference number — nudge IS the direct answer ── */
      case 4:
        setQuickReplies([])
        addTx(TX_STEP4, 0)
        after(500, () => {
          // Nudge answers the specific question using exact reference numbers
          setNudge('Your previous contact reference is INC-4412 (raised yesterday). Fraud case reference is FC-0291 — cleared by the fraud team on 25 May at 09:14.')
          setQuickReplies([
            'Your case reference from yesterday is INC-4412. Your fraud case is FC-0291 — cleared on 25 May at 09:14.',
            'INC-4412 is your previous complaint reference. FC-0291 is the fraud case — the review team cleared it yesterday morning.',
            'The references are INC-4412 (your complaint) and FC-0291 (fraud case, status: cleared). I can see both on my screen.',
          ])
          setNextAction('Give both reference numbers then move to removing the hold')
        })
        break

      /* ── 5: Companion full analysis — risk flags, action card; agent peeks Manual tab ── */
      case 5:
        setChecklist(CHECKLIST_STEP5)
        addTx([{ speaker: 'agent', text: TX_STEP5_AGENT }], 0)
        pushMood('frustrated')
        setResolutionProb(0.30)
        setRiskFlags(['repeat_complaint', 'unresolved_ai_attempt', 'active_hold_detected'])
        setInsight('FC-0291 cleared 25 May 09:14 — hold is 100% a stale system artifact. No fraud risk. Lift immediately and follow with unlock.')
        setKbSuggestion(KB_FRAUD_OPS)
        setAcwPreview({ summary: 'Stale fraud hold — fraud case cleared. Customer on second contact.', likely_resolution: 'unresolved' })
        after(400, () => {
          setSuggestedActions([ACTION_REMOVE_FRAUD_HOLD])
          setNudge('The hold is a stale system artifact — safe to remove right now. Salary may be trapped in the account — acknowledge this urgency.')
          setQuickReplies([])
          addEvent('action_suggested', 'remove_fraud_hold', 'AI suggested: Remove Fraud Hold — FC-0291')
        })
        // Agent peeks at the Manual tab to orient themselves, then confirms companion action is right
        if (setRightTab) {
          after(1200, () => setRightTab('toolkit'))
          after(3800, () => setRightTab('companion'))
        }
        break

      /* ── 6: Customer asks about documents — nudge changes to answer directly ── */
      case 6:
        addTx(TX_STEP6, 0)
        after(600, () => {
          // Nudge changes completely to answer the new question
          setNudge('No documents required. Fraud review is already complete (FC-0291 cleared). This is a system sync issue — no identity re-verification needed.')
          setQuickReplies([
            'No documents required at all — the fraud team completed the review and cleared FC-0291. This is purely a system delay.',
            'You don\'t need to provide anything — your case is fully cleared. I\'m removing the hold right now.',
          ])
          setNextAction('Remove fraud hold using the action card — no further information needed from customer')
        })
        break

      /* ── 7: Agent approves Remove Fraud Hold → executing → completed ── */
      case 7:
        setQuickReplies([])
        addTx(TX_STEP7_START, 0)
        after(400, () => {
          setActionStatuses(prev => ({ ...prev, remove_fraud_hold: 'executing' }))
          addEvent('action_approved', 'remove_fraud_hold', 'Agent approved: Remove Fraud Hold — FC-0291')
        })
        after(1800, () => {
          setActionStatuses(prev => ({ ...prev, remove_fraud_hold: 'completed' }))
          addEvent('action_executed', 'remove_fraud_hold', 'Fraud hold lifted — card transactions unblocked.')
          setLiveDoc(LIVE_DOC_POST_HOLD)
          setNudge('Fraud hold removed. Let Kavya know the hold is off, then unlock the account — that\'s the next step.')
        })
        break

      /* ── 8: Companion re-fires — agent switches to Manual tab to do unlock directly ── */
      case 8:
        setChecklist(CHECKLIST_STEP8)
        setKbSuggestion(null)
        setInsight('Fraud hold lifted successfully. Account lock is still active — must unlock as separate step. Salary access will restore immediately after.')
        pushMood('calm')
        setSentimentTrend('improving')
        setResolutionProb(0.72)
        setRiskFlags(['repeat_complaint'])
        setAcwPreview({ summary: 'Fraud hold removed. Unlocking account — full access within 60 seconds.', likely_resolution: 'resolved' })
        // First open question gets resolved (notification question irrelevant now)
        setOpenQuestions([DEMO_CASE_COMPLETE.open_questions[1]])
        after(400, () => {
          setSuggestedActions([ACTION_UNLOCK_ACCOUNT])
          setNudge('Unlock the account — that\'s the final step. Use the Manual tab to fire it directly, or approve the AI suggestion above.')
          setQuickReplies([
            'The hold is off. I\'m unlocking your account now — you should have full access including your salary within 60 seconds.',
            'Card, UPI, and transfers will all be re-enabled immediately once I confirm the unlock.',
          ])
          addTx(TX_STEP8, 0)
          addEvent('action_suggested', 'unlock_account', 'AI suggested: Unlock Account')
        })
        // Agent decides to use Manual tab directly instead of approving companion action
        if (setRightTab) after(1000, () => setRightTab('toolkit'))
        break

      /* ── 9: Agent fires Unlock Account via Manual Toolkit ── */
      case 9:
        setQuickReplies([])
        // Agent clicks in the Manual tab — toolkit shows running → ok
        after(300, () => {
          if (setToolkitStatuses) setToolkitStatuses(prev => ({ ...prev, unlock_account: 'running' }))
          if (setToolkitMessages) setToolkitMessages(prev => ({ ...prev, unlock_account: 'Unlocking account...' }))
          addEvent('action_approved', 'unlock_account', 'Manual Toolkit: Agent fired Unlock Account directly')
        })
        after(1800, () => {
          if (setToolkitStatuses) setToolkitStatuses(prev => ({ ...prev, unlock_account: 'ok' }))
          if (setToolkitMessages) setToolkitMessages(prev => ({ ...prev, unlock_account: 'Account unlocked — full access restored.' }))
          if (setToolkitRefs)     setToolkitRefs(prev => ({ ...prev, unlock_account: { res_number: 'RES-2026-0522' } }))
          addEvent('action_executed', 'unlock_account', 'Manual: Account unlocked — full access restored.')
          setLiveDoc(LIVE_DOC_FINAL)
          // Switch back to Companion tab after action completes
          if (setRightTab) setRightTab('companion')
        })
        addTx(TX_STEP9, 2200)
        break

      /* ── 10: Issue fully resolved — checklist done, satisfied mood ── */
      case 10:
        setChecklist(CHECKLIST_DONE)
        setSuggestedActions([])
        setOpenQuestions([])
        pushMood('satisfied')
        setSentimentHistory(prev => [...prev.slice(-7), { mood: 'calm' }, { mood: 'satisfied' }, { mood: 'satisfied' }])
        setSentimentTrend('improving')
        setResolutionProb(0.96)
        setRiskFlags([])
        setInsight('Both issues resolved. Customer confirmed card working. INC-4412 can be closed — reference RES-2026-0522.')
        setAcwPreview({ summary: 'Fraud hold and account lock lifted. Card working. Ref RES-2026-0522.', likely_resolution: 'resolved' })
        setNudge('Give Kavya resolution reference RES-2026-0522 and close the call warmly. Acknowledge the inconvenience of the repeat contact.')
        setQuickReplies([
          'Your resolution reference is RES-2026-0522 — please keep this for your records.',
          'I\'ve flagged the system sync issue to engineering so this doesn\'t happen to you again.',
          'Is there anything else I can help you with today?',
        ])
        addTx(TX_STEP10, 0)
        break

      /* ── 11: ACW generated instantly from live documentation ── */
      case 11:
        setQuickReplies([])
        setNudge(null)
        setAcwData(DEMO_ACW)
        setSummaryText(DEMO_ACW.summary)
        setResolution(DEMO_ACW.resolution)
        setCallerState('acw')
        break

      default:
        break
    }
  }, [
    setCallerState, setCallId, setCustomer, setHandoff, setVoiceTx, setLiveTx,
    setQuickReplies,
    setChecklist, setNudge, setNextAction, setCustomerMood, setKbSuggestion, setInsight,
    setAcwData, setSummaryText, setResolution, setAcwSubmitted,
    setSuggestedActions, setActionStatuses, setActivityTimeline, setSentimentHistory,
    setResolutionProb, setSentimentTrend, setRiskFlags, setAcwPreview,
    setCaseInvestigation, setOpenQuestions, setLiveDoc,
    setRightTab, setToolkitStatuses, setToolkitMessages, setToolkitRefs,
  ])

  return {
    runSimulation,
    nextStep,
    clearSim,
    simStep,
    simActive:      simStep >= 0,
    simTotalSteps:  SIM_TOTAL_STEPS,
  }
}
