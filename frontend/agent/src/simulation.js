/**
 * SIMULATION MODULE — delete this file and its 3 references in App.jsx to remove.
 * Search for "// SIM" in App.jsx to find every reference.
 *
 * Scenario: Kavya Reddy — fraud hold not lifted after clearance (sync delay).
 * 9 interactive steps, each triggered by Space / Enter.
 * Showcases the full HITL orchestration loop end-to-end.
 *
 * Step 0  Ready          — demo mode entered, waiting for first ⎵
 * Step 1  Incoming Call  — call rings, customer card + Voice AI transcript appear
 * Step 2  Call Accepted  — agent accepts, customer speaks first
 * Step 3  Agent Replies  — agent uses a quick reply, customer responds
 * Step 4  AI Analyzes    — Companion fires: risk flags, 30% resolution,
 *                           "Remove Fraud Hold" action + 3 quick replies
 * Step 5  Approve #1     — agent approves → hold lifted, companion nudges
 * Step 6  AI Suggests    — Companion re-fires: calm mood, 72% resolution,
 *                           "Unlock Account" action + quick replies
 * Step 7  Approve #2     — agent approves → account unlocked,
 *                           customer confirms card works
 * Step 8  Resolved       — satisfied mood, 93% resolution, full checklist done
 * Step 9  ACW            — after-call work summary generated
 */
import { useRef, useState, useCallback } from 'react'

function ts() { return new Date().toTimeString().split(' ')[0] }

export const SIM_TOTAL_STEPS = 9

export const SIM_STEP_LABELS = {
  0: 'Ready',
  1: 'Incoming Call',
  2: 'Call Accepted',
  3: 'Agent & Customer',
  4: 'Companion Analyzes',
  5: 'Fraud Hold Lifted',
  6: 'Companion Re-Fires',
  7: 'Account Unlocked',
  8: 'Issue Resolved',
  9: 'ACW Summary',
}

/* ── Demo data ─────────────────────────────────────────────────── */

const DEMO_CUSTOMER = {
  name:         'Kavya Reddy',
  email:        'kavya.reddy@email.com',
  account_type: 'premium',
  intent:       'account_access',
}

const DEMO_HANDOFF = {
  reason:
    'Account locked + fraud hold active since 24 May. Fraud review team marked case CLEARED ' +
    'on 25 May at 09:14 but system hold was never lifted (sync delay). Customer called yesterday ' +
    '(INC-4412) without resolution. Escalating for manual lift.',
  customer_id:   'CUST-demo-001',
  workflow_type: 'fraud_report',
}

const DEMO_VOICE_TX = [
  { speaker: 'voice_ai', text: 'Hi, this is Fin. How can I help you today?',                              time: '10:41:03' },
  { speaker: 'customer', text: 'My account is completely locked. My card is being declined everywhere.',   time: '10:41:09' },
  { speaker: 'voice_ai', text: 'I\'m sorry to hear that. Let me pull up your account.',                   time: '10:41:13' },
  { speaker: 'customer', text: 'My phone number is +91 87654 32109.',                                     time: '10:41:18' },
  { speaker: 'voice_ai', text: 'Thank you, Kavya. There\'s a fraud hold from 24 May — your fraud team cleared this yesterday but the hold is still active. I\'m connecting you to a specialist who can lift it immediately.', time: '10:41:26' },
  { speaker: 'customer', text: 'I called yesterday too! Nothing changed!',                                 time: '10:41:35' },
  { speaker: 'voice_ai', text: 'Understood. I\'m escalating you to a senior agent right now.',             time: '10:41:41' },
]

const TX_STEP2 = [
  { speaker: 'customer', text: 'Hello? Is someone there? I\'ve been dealing with this for two days now.' },
]

const TX_STEP3_AGENT = 'Hi Kavya — I\'m here. I can see your full case: fraud hold from May 24th, cleared by the fraud team yesterday at 09:14. This is a sync issue on our end. I\'m lifting it right now.'
const TX_STEP3 = [
  { speaker: 'agent',    text: TX_STEP3_AGENT },
  { speaker: 'customer', text: 'Thank goodness. My salary just came in and I can\'t even withdraw. This is the second time I\'m calling — reference INC-4412.' },
]

const TX_STEP5 = [
  { speaker: 'agent',    text: 'I\'m removing the fraud hold now — your card should work within 60 seconds.' },
  { speaker: 'customer', text: 'Okay. How long does this actually take?' },
]

const TX_STEP7 = [
  { speaker: 'customer', text: 'Oh! My card just worked! I can\'t believe it finally worked!' },
  { speaker: 'agent',    text: 'Both the fraud hold and account lock are now fully lifted. Your resolution reference is RES-2026-0522. I\'ve also flagged the sync delay for our engineering team.' },
]

const TX_STEP8 = [
  { speaker: 'customer', text: 'Thank you so much. Really appreciate it.' },
  { speaker: 'agent',    text: 'You\'re very welcome, Kavya. Take care!' },
]

/* ── Companion payloads ────────────────────────────────────────── */

const CHECKLIST_INITIAL = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: false },
  { step: 'Confirm fraud clearance note (CLEARED, 25 May 09:14)', done: false },
  { step: 'Remove fraud hold via Operational Actions',            done: false },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_STEP5 = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true },
  { step: 'Confirm fraud clearance note (CLEARED, 25 May 09:14)', done: true },
  { step: 'Remove fraud hold via Operational Actions',            done: false },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_STEP6 = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true },
  { step: 'Confirm fraud clearance note (CLEARED, 25 May 09:14)', done: true },
  { step: 'Remove fraud hold via Operational Actions',            done: true },
  { step: 'Unlock account once hold is lifted',                   done: false },
  { step: 'Confirm card working and give resolution reference',   done: false },
]
const CHECKLIST_DONE = [
  { step: 'Greet Kavya and acknowledge the repeat escalation',    done: true },
  { step: 'Confirm fraud clearance note (CLEARED, 25 May 09:14)', done: true },
  { step: 'Remove fraud hold via Operational Actions',            done: true },
  { step: 'Unlock account once hold is lifted',                   done: true },
  { step: 'Confirm card working and give resolution reference',   done: true },
]

const ACTION_REMOVE_FRAUD_HOLD = {
  id:               'remove_fraud_hold',
  label:            'Remove Fraud Hold',
  description:      'Lift the system fraud hold placed on 24 May 2026',
  reason:           'Fraud team marked case CLEARED on 25 May 09:14. Hold is a stale system artifact — no active risk.',
  impact:           'Unblocks card transactions immediately. Required before account can be unlocked.',
  confidence:       0.88,
  priority:         'high',
  risk:             'medium',
  requires_approval: true,
  payload:          { customer_id: 'CUST-demo-001' },
}

const ACTION_UNLOCK_ACCOUNT = {
  id:               'unlock_account',
  label:            'Unlock Account',
  description:      'Restore full account access after fraud clearance',
  reason:           'Fraud hold successfully removed. Account lock can now be safely lifted — no remaining restrictions.',
  impact:           'Customer regains full access: card, UPI, and transfers all enabled immediately.',
  confidence:       0.92,
  priority:         'high',
  risk:             'low',
  requires_approval: true,
  payload:          { customer_id: 'CUST-demo-001' },
}

const KB_FRAUD_OPS = {
  source:  'fraud_operations.md',
  content: 'Fraud hold removal: once the fraud review team marks a case CLEARED, the account manager may remove the hold immediately without additional approval. Effect is immediate (≤60 seconds). Account unlock must follow as a separate step.',
}

const DEMO_ACW = {
  summary:
    'Kavya Reddy called regarding a fraud hold that persisted after the fraud team cleared her case on 25 May 09:14. ' +
    'Specialist confirmed the clearance note, removed the fraud hold, and unlocked the account via the Operational Actions panel. ' +
    'Customer confirmed card working immediately after. Second contact for same issue — INC-4412 did not resolve due to a sync delay. ' +
    'Resolution reference: RES-2026-0522.',
  resolution:   'resolved',
  action_items: [
    'Engineering: investigate fraud-hold sync delay between fraud review system and card system',
    'Flag INC-4412 as resolved — reference RES-2026-0522',
    'Send resolution SMS + email to Kavya Reddy (+91 87654 32109)',
  ],
  coaching_note:
    'Strong ownership of a repeat escalation — immediately acknowledged prior contact and took full responsibility. ' +
    'Consider surfacing the KB fraud policy at step 3 to set timeline expectations before the customer asks.',
  crm_fields: {
    issue_type:     'fraud_account_hold',
    resolution_ref: 'RES-2026-0522',
    notes:          'Stale fraud hold lifted manually. Engineering flagged for sync delay investigation.',
  },
}

/* ── Hook ──────────────────────────────────────────────────────── */

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
      after(baseMs + i * 900, () =>
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
  }, [
    setCallerState, setCallId, setCustomer, setHandoff, setVoiceTx, setLiveTx,
    setQuickReplies,
    setChecklist, setNudge, setNextAction, setCustomerMood, setKbSuggestion, setInsight,
    setAcwData, setSummaryText, setResolution, setAcwSubmitted,
    setSuggestedActions, setActionStatuses, setActivityTimeline, setSentimentHistory,
    setResolutionProb, setSentimentTrend, setRiskFlags, setAcwPreview,
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

      /* 1 — Incoming call rings */
      case 1:
        setCallId('demo-call-001')
        setCustomer(DEMO_CUSTOMER)
        setHandoff(DEMO_HANDOFF)
        setVoiceTx(DEMO_VOICE_TX)
        setCallerState('incoming')
        break

      /* 2 — Agent accepts, customer speaks first */
      case 2:
        setLiveTx([{ speaker: 'system', text: 'Call connected — Kavya Reddy is on the line.', time: ts() }])
        setCallerState('active')
        addTx(TX_STEP2, 700)
        // Companion fires immediately with opening quick replies
        after(1000, () => {
          setQuickReplies([
            'Hi Kavya — I\'m here. I can see your full case and the fraud team\'s clearance note from yesterday.',
            'I can see this is your second contact about the same issue — I\'m resolving this right now.',
            'Don\'t worry Kavya, I have everything I need to fix this immediately.',
          ])
          setNextAction('Greet Kavya and confirm you can see the fraud clearance note')
          setChecklist(CHECKLIST_INITIAL)
        })
        break

      /* 3 — Agent uses quick reply, customer responds */
      case 3:
        setQuickReplies([])
        addTx(TX_STEP3, 0)
        break

      /* 4 — Companion AI fires: risk flags, action suggested */
      case 4:
        setChecklist(CHECKLIST_INITIAL)
        setNextAction('Remove the fraud hold immediately using the Operational Actions panel — Kavya needs her card working now.')
        pushMood('frustrated')
        setResolutionProb(0.30)
        setSentimentTrend('stable')
        setRiskFlags(['repeat_complaint', 'unresolved_ai_attempt'])
        setInsight('Fraud team cleared this at 09:14 yesterday. Hold is a stale sync artifact — no active risk. Lift it immediately.')
        setAcwPreview({ summary: 'Customer calling about stale fraud hold — fraud team already cleared the case.', likely_resolution: 'unresolved' })

        after(400, () => {
          setSuggestedActions([ACTION_REMOVE_FRAUD_HOLD])
          setQuickReplies([
            'I can confirm the fraud team cleared your case yesterday at 09:14 — the hold is a system delay on our end, not a fraud risk.',
            'I\'m approving the hold removal right now — you should have card access back within 60 seconds.',
          ])
          addEvent('action_suggested', 'remove_fraud_hold', 'AI suggested: Remove Fraud Hold')
        })
        break

      /* 5 — Agent approves Remove Fraud Hold */
      case 5:
        setChecklist(CHECKLIST_STEP5)
        setNudge('Acknowledge the repeat contact: "I can see you called yesterday" — builds immediate trust.')
        setKbSuggestion(KB_FRAUD_OPS)
        setQuickReplies([])
        addTx(TX_STEP5, 0)

        after(400, () => {
          setActionStatuses(prev => ({ ...prev, remove_fraud_hold: 'executing' }))
          addEvent('action_approved', 'remove_fraud_hold', 'Agent approved: Remove Fraud Hold')
        })
        after(1800, () => {
          setActionStatuses(prev => ({ ...prev, remove_fraud_hold: 'completed' }))
          addEvent('action_executed', 'remove_fraud_hold', 'Fraud hold lifted — card transactions unblocked.')
        })
        break

      /* 6 — Companion re-fires: Unlock Account */
      case 6:
        setChecklist(CHECKLIST_STEP6)
        setNudge(null)
        setKbSuggestion(null)
        setInsight('Fraud hold lifted successfully. Account lock still active — must be removed as a separate step.')
        pushMood('calm')
        setSentimentTrend('improving')
        setResolutionProb(0.72)
        setRiskFlags(['repeat_complaint'])
        setAcwPreview({ summary: 'Fraud hold removed. Unlocking account — full access within 60 seconds.', likely_resolution: 'resolved' })

        after(400, () => {
          setSuggestedActions([ACTION_UNLOCK_ACCOUNT])
          setQuickReplies([
            'The fraud hold is lifted. I\'m now unlocking your account — full access in under 60 seconds.',
            'Your card, UPI, and transfers will all be re-enabled immediately once I confirm.',
          ])
          addEvent('action_suggested', 'unlock_account', 'AI suggested: Unlock Account')
        })
        break

      /* 7 — Agent approves Unlock Account, customer confirms */
      case 7:
        setQuickReplies([])
        after(300, () => {
          setActionStatuses(prev => ({ ...prev, unlock_account: 'executing' }))
          addEvent('action_approved', 'unlock_account', 'Agent approved: Unlock Account')
        })
        after(1600, () => {
          setActionStatuses(prev => ({ ...prev, unlock_account: 'completed' }))
          addEvent('action_executed', 'unlock_account', 'Account unlocked — full access restored.')
        })
        addTx(TX_STEP7, 2000)
        break

      /* 8 — Issue resolved */
      case 8:
        setChecklist(CHECKLIST_DONE)
        setSuggestedActions([])
        pushMood('satisfied')
        setSentimentTrend('improving')
        setResolutionProb(0.93)
        setRiskFlags([])
        setInsight('Both issues resolved. Customer confirmed card working. Engineering flag added for sync delay follow-up.')
        setAcwPreview({ summary: 'Fraud hold and account lock lifted. Customer confirmed card working. Ref RES-2026-0522.', likely_resolution: 'resolved' })
        setQuickReplies([
          'Your reference number is RES-2026-0522 — please keep this for your records.',
          'You\'re all set, Kavya. I\'ve also flagged this sync delay so it doesn\'t happen again.',
          'Is there anything else I can help you with today?',
        ])
        addTx(TX_STEP8, 0)
        after(1200, () => {
          setNudge('Give Kavya resolution reference RES-2026-0522 and close warmly.')
        })
        break

      /* 9 — ACW generated */
      case 9:
        setQuickReplies([])
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
