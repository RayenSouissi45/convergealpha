import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatEur } from '../lib/costs'
import type { Fan } from '../lib/goal'

const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })

/** How the plan's value spreads out over the years across the replayed futures: the middle line,
 * the middle half and 8 of 10 futures as bands of one hue, the money paid in and the goal as
 * neutral dashed references. */
export default function GoalChart({ data, goal, real }: { data: Fan[]; goal: number; real: boolean }) {
  const rows = data.map((d) => ({ ...d, outer: [d.p10, d.p90] as [number, number], inner: [d.p25, d.p75] as [number, number] }))
  const last = data.at(-1)
  const unit = real ? "today's euros" : 'euros'
  return (
    <figure>
      <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-700 dark:text-zinc-300" aria-label="Legend">
        <li className="inline-flex items-center gap-1.5">
          <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinecap="round" /></svg>
          Middle outcome
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: 'var(--viz-series-1)', opacity: 0.35 }} aria-hidden="true" />
          Middle half of futures
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: 'var(--viz-series-1)', opacity: 0.15 }} aria-hidden="true" />8 of 10 futures
        </li>
        <li className="inline-flex items-center gap-1.5">
          <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-ref)" strokeWidth={2} strokeDasharray="4 3" /></svg>
          Money paid in{real ? ' (euros, not adjusted for inflation)' : ''}
        </li>
        {goal > 0 && (
          <li className="inline-flex items-center gap-1.5">
            <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-axis)" strokeWidth={1.25} strokeDasharray="2 3" /></svg>
            Your goal
          </li>
        )}
      </ul>
      <div className="h-64 w-full sm:h-72" role="img" aria-label={`Plan value over ${data.length - 1} years in ${unit}. After ${data.length - 1} years: middle ${last ? formatEur(last.p50, 0) : '—'}, 8 of 10 futures between ${last ? formatEur(last.p10, 0) : '—'} and ${last ? formatEur(last.p90, 0) : '—'}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
            <XAxis dataKey="year" tickFormatter={(y: number) => `${y}y`} tick={{ fill: 'var(--viz-axis)', fontSize: 11 }} minTickGap={16} />
            <YAxis tickFormatter={(v: number) => `€${compact.format(v)}`} tick={{ fill: 'var(--viz-axis)', fontSize: 11 }} width={52} />
            <Tooltip
              formatter={(v, name) => {
                const label = name === 'outer' ? '8 of 10 futures' : name === 'inner' ? 'Middle half' : name === 'p50' ? 'Middle outcome' : 'Money paid in'
                const text = Array.isArray(v) ? `${formatEur(Number(v[0]), 0)} to ${formatEur(Number(v[1]), 0)}` : formatEur(Number(v), 0)
                return [text, label]
              }}
              labelFormatter={(y) => `After ${String(y)} year${Number(y) === 1 ? '' : 's'}`}
              contentStyle={{ borderRadius: 8, fontSize: 12 }}
              wrapperClassName="!text-slate-900"
              cursor={{ stroke: 'var(--viz-axis)', strokeWidth: 1 }}
            />
            <Area dataKey="outer" stroke="none" fill="var(--viz-series-1)" fillOpacity={0.15} isAnimationActive={false} />
            <Area dataKey="inner" stroke="none" fill="var(--viz-series-1)" fillOpacity={0.35} isAnimationActive={false} />
            <Line dataKey="paidIn" stroke="var(--viz-ref)" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line dataKey="p50" stroke="var(--viz-series-1)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            {goal > 0 && <ReferenceLine y={goal} stroke="var(--viz-axis)" strokeDasharray="2 3" ifOverflow="extendDomain" />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-slate-500 dark:text-zinc-400">In {unit}. Each future replays real years of market history in random order; the bands show where most of them ended.</figcaption>
    </figure>
  )
}
