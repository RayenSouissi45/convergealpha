import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatEur } from '../../lib/costs'
import type { MonthPoint } from '../../lib/vsMarket'

/** Your money month by month next to the same trades in the S&P 500, and the euros paid in. */
export default function MoneyChart({ data }: { data: MonthPoint[] }) {
  return (
    <figure>
      <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-700 dark:text-zinc-300" aria-label="Legend">
        <li className="inline-flex items-center gap-1.5">
          <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinecap="round" /></svg>
          You
        </li>
        <li className="inline-flex items-center gap-1.5">
          <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-ref)" strokeWidth={2} strokeDasharray="4 3" /></svg>
          Same trades in the S&P 500
        </li>
        <li className="inline-flex items-center gap-1.5">
          <svg width="18" height="8" aria-hidden="true"><line x1="1" y1="4" x2="17" y2="4" stroke="var(--viz-axis)" strokeWidth={1.5} /></svg>
          Paid in
        </li>
      </ul>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--viz-axis)' }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--viz-axis)' }} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => formatEur(v, 0)} />
            <Tooltip formatter={(v) => (typeof v === 'number' ? formatEur(v, 0) : String(v ?? ''))} />
            <Line type="monotone" dataKey="paidIn" name="Paid in" stroke="var(--viz-axis)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="market" name="Same trades in the S&P 500" stroke="var(--viz-ref)" strokeWidth={2} strokeDasharray="4 3" dot={false} />
            <Line type="monotone" dataKey="you" name="You" stroke="var(--viz-series-1)" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">Your money by month end, the same trades in the S&P 500, and the euros paid in.</figcaption>
    </figure>
  )
}
