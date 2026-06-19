import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Dot } from 'recharts'

const Y  = '#f4f73d'
const Ya = (a) => `rgba(244,247,61,${a})`
const Wa = (a) => `rgba(255,255,255,${a})`

function fmt(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    + ' ' + d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const isPassing = d.pass_fail === 'PASS'
  return (
    <div className="rounded-xl px-3 py-2.5" style={{ background: '#111', border: `1px solid ${Wa(0.14)}`, minWidth: 160 }}>
      <p style={{ fontSize: 12, color: '#fff', fontWeight: 500, marginBottom: 4 }}>
        {d.label}
      </p>
      <p style={{ fontSize: 11, color: Wa(0.45), marginBottom: 6 }}>{fmt(d.call_started_at)}</p>
      <div className="flex items-center justify-between gap-4">
        <span style={{ fontSize: 20, fontWeight: 300, color: isPassing ? Y : '#fc535b' }}>
          {d.overall_score}
        </span>
        <span style={{
          fontSize: 9, letterSpacing: '1px', textTransform: 'uppercase',
          padding: '2px 7px', borderRadius: 99,
          color: isPassing ? Y : '#fc535b',
          background: isPassing ? Ya(0.1) : 'rgba(252,83,91,0.1)',
          border: `1px solid ${isPassing ? Ya(0.25) : 'rgba(252,83,91,0.3)'}`,
        }}>
          {d.pass_fail}
        </span>
      </div>
    </div>
  )
}

function CustomDot(props) {
  const { cx, cy, payload } = props
  const color = payload.pass_fail === 'PASS' ? Y : '#fc535b'
  return <circle cx={cx} cy={cy} r={4} fill={color} stroke="none" />
}

function CustomActiveDot(props) {
  const { cx, cy, payload } = props
  const color = payload.pass_fail === 'PASS' ? Y : '#fc535b'
  return <circle cx={cx} cy={cy} r={6} fill={color} stroke={color} strokeOpacity={0.3} strokeWidth={4} />
}

export default function TrendChart({ evals }) {
  const data = [...(evals || [])]
    .sort((a, b) => new Date(a.call_started_at) - new Date(b.call_started_at))
    .map((e, i) => ({
      ...e,
      label: e.customer_name || `Call ${i + 1}`,
      tick: e.customer_name
        ? e.customer_name.split(' ')[0]
        : `#${i + 1}`,
    }))

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: Wa(0.025), border: `1px solid ${Wa(0.07)}` }}
    >
      <div className="flex items-center justify-between mb-5">
        <p className="section-label">Call QA Scores</p>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, borderRadius: 2, background: Y, display: 'inline-block' }} />
            <span className="t-caps text-white/45 text-[10px]">Pass</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, borderRadius: 2, background: '#fc535b', display: 'inline-block' }} />
            <span className="t-caps text-white/45 text-[10px]">Fail</span>
          </div>
        </div>
      </div>

      {!data.length ? (
        <div className="flex flex-col items-center justify-center" style={{ height: 180 }}>
          <p className="t-body-14 text-white/35">No QA scores yet</p>
          <p className="t-caps text-white/22 mt-1.5" style={{ fontSize: 10 }}>Scores appear within seconds of a call ending</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={Wa(0.05)} vertical={false} />
            <XAxis
              dataKey="tick"
              tick={{ fill: Wa(0.42), fontSize: 11, fontFamily: 'Aeonik, system-ui' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: Wa(0.42), fontSize: 11, fontFamily: 'Aeonik, system-ui' }}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceLine y={70} stroke={Wa(0.12)} strokeDasharray="4 4" />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: Wa(0.08), strokeWidth: 1 }} />
            <Line
              type="monotone"
              dataKey="overall_score"
              stroke={Ya(0.5)}
              strokeWidth={1.5}
              dot={<CustomDot />}
              activeDot={<CustomActiveDot />}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
