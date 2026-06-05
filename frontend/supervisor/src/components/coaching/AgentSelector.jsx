const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function initials(name = '') {
  return name.split(' ').map(p => p[0] || '').join('').toUpperCase().slice(0, 2)
}

export default function AgentSelector({ agents, selectedId, onSelect }) {
  if (!agents.length) {
    return (
      <div
        className="rounded-2xl p-8 text-center"
        style={{ background: Wa(0.02), border: `1px solid ${Wa(0.06)}` }}
      >
        <p className="t-body-14 text-white/45">No agents found</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {agents.map(agent => {
        const selected    = agent.agent_id === selectedId
        const canGenerate = agent.scored_calls >= 3

        return (
          <div
            key={agent.agent_id}
            onClick={() => onSelect(agent)}
            className="flex items-center gap-3 rounded-2xl px-4 py-3.5 cursor-pointer transition-all"
            style={{
              background: selected ? Ya(0.06) : Wa(0.02),
              border: `1px solid ${selected ? Ya(0.22) : Wa(0.06)}`,
            }}
            onMouseEnter={e => { if (!selected) e.currentTarget.style.background = Wa(0.035) }}
            onMouseLeave={e => { if (!selected) e.currentTarget.style.background = Wa(0.02) }}
          >
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 text-[12px] font-bold"
              style={{
                background: selected ? Ya(0.10) : Wa(0.05),
                border: `1px solid ${selected ? Ya(0.28) : Wa(0.10)}`,
                color: selected ? Y : Wa(0.65),
              }}
            >
              {initials(agent.name)}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-white">{agent.name}</p>
              <p className="t-caps text-white/42 text-[10px]">{agent.team || 'Support'}</p>
            </div>

            <div className="text-right flex-shrink-0">
              <p
                className="t-caps text-[10px]"
                style={{ color: canGenerate ? Y : Wa(0.38) }}
              >
                {agent.scored_calls} scored
              </p>
              {!canGenerate && (
                <p className="t-caps text-white/28 text-[10px] mt-0.5">Need 3+</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
