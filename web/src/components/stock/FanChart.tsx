import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export interface FanPoint {
  label: string
  days: number
  median: number
  band: [number, number]
}

const pct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(0)}%`

/** Median forecast with the 10th–90th percentile band, by horizon. */
export default function FanChart({ points }: { points: FanPoint[] }) {
  const data = [{ label: 'Today', days: 0, median: 0, band: [0, 0] as [number, number] }, ...points]
  return (
    <div
      className="h-52 w-full"
      role="img"
      aria-label={`Forecast range: ${points.map((p) => `${p.label} median ${pct(p.median)}, 10th to 90th percentile ${pct(p.band[0])} to ${pct(p.band[1])}`).join('; ')}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: 'var(--viz-axis)', fontSize: 12 }} axisLine={{ stroke: 'var(--viz-grid)' }} tickLine={false} />
          <YAxis tickFormatter={pct} tick={{ fill: 'var(--viz-axis)', fontSize: 12 }} axisLine={false} tickLine={false} width={48} />
          <ReferenceLine y={0} stroke="var(--viz-ref)" />
          <Tooltip
            formatter={(v, name) => (Array.isArray(v) ? [`${pct(Number(v[0]))} to ${pct(Number(v[1]))}`, '10th–90th percentile'] : [pct(Number(v)), name === 'median' ? 'Median' : String(name)])}
            contentStyle={{ borderRadius: 8, fontSize: 12 }}
            wrapperClassName="!text-slate-900"
          />
          <Area type="monotone" dataKey="band" stroke="none" fill="var(--viz-series-1)" fillOpacity={0.12} isAnimationActive={false} />
          <Line type="monotone" dataKey="median" stroke="var(--viz-series-1)" strokeWidth={2} dot={{ r: 4, fill: 'var(--viz-series-1)', strokeWidth: 0 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
