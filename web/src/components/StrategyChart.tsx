import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatEur } from '../lib/costs'
import { formatDay } from '../lib/format'

export interface ChartSeries {
  key: string
  name: string
  /** CSS colour; the benchmark uses the neutral reference colour, dashed. */
  color: string
  dashed?: boolean
  /** A dotted line in the strategy's colour: the same rules on the other set of stocks. */
  dotted?: boolean
  points: [string, number][]
}

/** Value of each strategy in euros, all starting at 200 €. Colour follows the strategy (fixed
 * order), the S&P 500 is a dashed neutral line; the legend and the leaderboard table name them. */
export default function StrategyChart({ series, start }: { series: ChartSeries[]; start: number }) {
  const dates = [...new Set(series.flatMap((s) => s.points.map(([d]) => d)))].sort()
  const data = dates.map((d) => ({ date: d, ...Object.fromEntries(series.map((s) => [s.key, s.points.find(([x]) => x === d)?.[1] ?? null])) }))
  const values = series.flatMap((s) => s.points.map(([, v]) => v))
  const lo = Math.floor(Math.min(start, ...values) / 5) * 5 - 5
  const hi = Math.ceil(Math.max(start, ...values) / 5) * 5 + 5
  const few = dates.length <= 2
  const last = dates[dates.length - 1]
  const summary = series.map((s) => `${s.name} ${formatEur(s.points[s.points.length - 1]?.[1] ?? start)}`).join('; ')
  return (
    <figure>
      <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Legend">
        {series.map((s) => (
          <li key={s.key} className="inline-flex items-center gap-1.5 text-slate-700 dark:text-zinc-300">
            <svg width="18" height="8" aria-hidden="true">
              <line x1="1" y1="4" x2="17" y2="4" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '4 3' : s.dotted ? '1 3' : undefined} strokeLinecap="round" />
            </svg>
            {s.name}
          </li>
        ))}
      </ul>
      <div className="h-64 w-full sm:h-72" role="img" aria-label={`Value in euros since ${formatDay(dates[0] ?? last ?? '2026-10-13')}. Latest: ${summary}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d: string) => formatDay(d).replace(/, \d{4}$/, '')} tick={{ fill: 'var(--viz-axis)', fontSize: 11 }} minTickGap={24} />
            <YAxis domain={[lo, hi]} tickFormatter={(v: number) => `€${v}`} tick={{ fill: 'var(--viz-axis)', fontSize: 11 }} width={48} />
            <ReferenceLine y={start} stroke="var(--viz-ref)" strokeDasharray="2 3" />
            <Tooltip
              formatter={(v, name) => [formatEur(Number(v)), series.find((s) => s.key === name)?.name ?? String(name)]}
              labelFormatter={(d) => formatDay(String(d))}
              itemSorter={(item) => -Number(item.value)}
              contentStyle={{ borderRadius: 8, fontSize: 12 }}
              wrapperClassName="!text-slate-900"
              cursor={{ stroke: 'var(--viz-axis)', strokeWidth: 1 }}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                type="linear"
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dashed ? '5 4' : s.dotted ? '1 4' : undefined}
                strokeLinecap={s.dotted ? 'round' : undefined}
                dot={few ? { r: 4, fill: s.color, strokeWidth: 2, stroke: 'var(--color-white, #fff)' } : false}
                activeDot={{ r: 4 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {few && <figcaption className="mt-1 text-xs text-slate-500 dark:text-zinc-400">Every line starts at {formatEur(start, 0)}. They move apart once the first orders fill and prices change.</figcaption>}
    </figure>
  )
}
