import { Bot } from 'lucide-react'
import ChecklistPanel from './ChecklistPanel.jsx'
import NudgeAlert from './NudgeAlert.jsx'
import KBSuggestion from './KBSuggestion.jsx'
import NextAction from './NextAction.jsx'

export default function CompanionPanel({ companion, callActive }) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}
      >
        <Bot size={16} color="#f4f73d" />
        <span className="t-body-14 text-w-text font-medium">Companion AI</span>
        {callActive && (
          <div
            className="w-1.5 h-1.5 rounded-full ml-auto"
            style={{ background: '#f4f73d', animation: 'callPulse 2s infinite' }}
          />
        )}
      </div>

      {!callActive ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="t-body-14 text-w-hint text-center">
            Companion activates when a call arrives
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

          {/* Checklist */}
          <div>
            <p className="t-caps text-w-hint mb-2">Call Checklist</p>
            <ChecklistPanel checklist={companion?.checklist} />
          </div>

          {/* Next action */}
          <NextAction
            nextAction={companion?.next_action}
            customerMood={companion?.customer_mood}
          />

          {/* Nudge */}
          <NudgeAlert nudge={companion?.nudge} />

          {/* KB suggestion */}
          <KBSuggestion kbSuggestion={companion?.kb_suggestion} />

          {/* Insight */}
          {companion?.insight && (
            <div
              className="rounded-xl p-3"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              <p className="t-caps text-w-hint mb-1">Insight</p>
              <p className="t-body-12 text-w-muted">{companion.insight}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
