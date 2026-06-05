const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

const KPI_DEFS = [
  { key: 'total_calls',      label: 'Total Calls',   suffix: '',     featured: true },
  { key: 'resolved',         label: 'Resolved',      suffix: '',     featured: false },
  { key: 'escalated',        label: 'Escalated',     suffix: '',     featured: false },
  { key: 'avg_duration',     label: 'Avg Duration',  suffix: 's',    featured: false },
  { key: 'avg_score',        label: 'Avg QA Score',  suffix: '/100', featured: false },
  { key: 'containment_rate', label: 'Containment',   suffix: '%',    featured: false },
]

export default function KPIStrip({ kpis }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {KPI_DEFS.map(({ key, label, suffix, featured }) => {
        const value = kpis?.[key]
        return (
          <div
            key={key}
            className="rounded-2xl p-5 flex flex-col gap-2 transition-all"
            style={{
              background: featured ? Ya(0.06) : Wa(0.025),
              border: `1px solid ${featured ? Ya(0.18) : Wa(0.07)}`,
            }}
          >
            <p className="section-label" style={{ fontSize: 10, letterSpacing: '1.8px' }}>{label}</p>
            <p
              className="font-light tracking-tight leading-none"
              style={{ fontSize: featured ? 32 : 26, color: featured ? Y : '#fff' }}
            >
              {value != null ? `${value}${suffix}` : '—'}
            </p>
          </div>
        )
      })}
    </div>
  )
}
