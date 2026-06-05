import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div
      className="rounded-xl px-3 py-2.5"
      style={{ background: '#111', border: `1px solid ${Wa(0.12)}` }}
    >
      <p className="t-caps text-white/52 mb-1.5">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-[12px] font-medium" style={{ color: p.color }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

function generatePlaceholder() {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  return days.map(day => ({
    day,
    avg_score: 60 + Math.round(Math.random() * 30),
  }))
}

export default function TrendChart({ data }) {
  const chartData = data?.length ? data : generatePlaceholder()

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: 'rgba(255,255,255,0.025)', border: `1px solid ${Wa(0.07)}` }}
    >
      <div className="flex items-center justify-between mb-5">
        <p className="section-label">7-Day QA Score Trend</p>
        <div className="flex items-center gap-2">
          <span className="w-3 h-px" style={{ background: Y, display: 'inline-block' }} />
          <span className="t-caps text-white/45 text-[10px]">Avg QA Score</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={Wa(0.05)} vertical={false} />
          <XAxis
            dataKey="day"
            tick={{ fill: Wa(0.42), fontSize: 11, fontFamily: 'Aeonik, system-ui' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: Wa(0.42), fontSize: 11, fontFamily: 'Aeonik, system-ui' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: Wa(0.08), strokeWidth: 1 }} />
          <Line
            type="monotone"
            dataKey="avg_score"
            name="Avg QA Score"
            stroke={Y}
            strokeWidth={2}
            dot={{ fill: Y, r: 3, strokeWidth: 0 }}
            activeDot={{ r: 5, fill: Y, stroke: Ya(0.3), strokeWidth: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
