import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export interface EpsPoint {
  label: string
  eps: number
}

/** How this year's consensus EPS estimate moved over 90 days (single series: no legend). */
export default function EpsChart({ points }: { points: EpsPoint[] }) {
  return (
    <div className="h-44 w-full" role="img" aria-label={`EPS estimate: ${points.map((p) => `${p.label} ${p.eps.toFixed(2)}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: 'var(--viz-axis)', fontSize: 12 }} axisLine={{ stroke: 'var(--viz-grid)' }} tickLine={false} />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: 'var(--viz-axis)', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={(v: number) => `$${v.toFixed(2)}`}
          />
          <Tooltip
            formatter={(v) => [`$${Number(v).toFixed(2)}`, 'EPS estimate']}
            contentStyle={{ background: 'var(--color-white, #fff)', borderRadius: 8, fontSize: 12 }}
            wrapperClassName="!text-slate-900"
          />
          <Line
            type="monotone"
            dataKey="eps"
            stroke="var(--viz-series-1)"
            strokeWidth={2}
            dot={{ r: 4, fill: 'var(--viz-series-1)', stroke: 'var(--color-white, #fff)', strokeWidth: 2 }}
            activeDot={{ r: 6 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
