import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export interface ReliabilityPoint {
  predicted: number
  actual: number
  n: number
}

const pct = (v: number) => `${Math.round(v * 100)}%`

/** Predicted vs actual frequency. On the diagonal = well calibrated. Single series. */
export default function ReliabilityChart({ points, label }: { points: ReliabilityPoint[]; label: string }) {
  const lo = Math.max(0, Math.floor(Math.min(...points.map((p) => Math.min(p.predicted, p.actual))) * 10) / 10 - 0.05)
  const hi = Math.min(1, Math.ceil(Math.max(...points.map((p) => Math.max(p.predicted, p.actual))) * 10) / 10 + 0.05)
  return (
    <div className="h-56 w-full" role="img" aria-label={`${label}: ${points.map((p) => `predicted ${pct(p.predicted)}, happened ${pct(p.actual)} (${p.n})`).join('; ')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="var(--viz-grid)" />
          <XAxis type="number" dataKey="predicted" domain={[lo, hi]} tickFormatter={pct} tick={{ fill: 'var(--viz-axis)', fontSize: 12 }} label={{ value: 'Predicted', position: 'insideBottom', offset: -8, fill: 'var(--viz-axis)', fontSize: 12 }} />
          <YAxis type="number" dataKey="actual" domain={[lo, hi]} tickFormatter={pct} tick={{ fill: 'var(--viz-axis)', fontSize: 12 }} width={44} />
          <ReferenceLine segment={[{ x: lo, y: lo }, { x: hi, y: hi }]} stroke="var(--viz-ref)" strokeDasharray="0" ifOverflow="extendDomain" />
          <Tooltip formatter={(v, name) => [pct(Number(v)), name === 'actual' ? 'Happened' : 'Predicted']} labelFormatter={(v) => `Predicted ${pct(Number(v))}`} contentStyle={{ borderRadius: 8, fontSize: 12 }} wrapperClassName="!text-slate-900" />
          <Line type="monotone" dataKey="actual" stroke="var(--viz-series-1)" strokeWidth={2} dot={{ r: 4, fill: 'var(--viz-series-1)', strokeWidth: 0 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
