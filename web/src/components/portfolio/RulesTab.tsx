import { formatDay } from '../../lib/format'
import { DEFAULT_RULES, type Journal, type Rules } from '../../lib/journal'
import { Card } from '../ui'

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'

/** Your own investment rules, written down before you invest (an investment policy statement).
 * Every trade you log is checked against them. */
export function RulesTab({ j, setJ }: { j: Journal; setJ: (j: Journal) => void }) {
  const r = j.rules
  const set = (patch: Partial<Rules>) => setJ({ ...j, rules: { ...r, ...patch, createdOn: r.createdOn ?? new Date().toISOString().slice(0, 10) } })
  const num = (v: string, d: number) => (Number.isFinite(Number(v)) && v !== '' ? Number(v) : d)
  return (
    <Card title="My rules">
      <p className="mb-3 text-sm text-slate-600 dark:text-zinc-400">
        Write them down while you are calm. Every trade you log is checked against them, and the Review tab shows how often you followed them.
        {r.createdOn ? ` Written ${formatDay(r.createdOn)}.` : ''}
      </p>
      <label className="block text-sm font-medium">
        What the money is for
        <input className={input} value={r.goal} onChange={(e) => set({ goal: e.target.value })} placeholder="e.g. a flat deposit in 10 years" />
      </label>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <label className="text-sm font-medium">
          Years until I need it
          <input className={input} type="number" min={1} max={60} value={r.horizonYears} onChange={(e) => set({ horizonYears: num(e.target.value, DEFAULT_RULES.horizonYears) })} />
        </label>
        <label className="text-sm font-medium">
          Biggest fall I can live with (%)
          <input className={input} type="number" min={1} max={100} value={Math.round(r.maxLoss * 100)} onChange={(e) => set({ maxLoss: num(e.target.value, 20) / 100 })} />
        </label>
        <label className="text-sm font-medium">
          Most stocks at once
          <input className={input} type="number" min={1} max={100} value={r.maxPositions} onChange={(e) => set({ maxPositions: num(e.target.value, DEFAULT_RULES.maxPositions) })} />
        </label>
        <label className="text-sm font-medium">
          Most in one stock (%)
          <input className={input} type="number" min={1} max={100} value={Math.round(r.maxPerStock * 100)} onChange={(e) => set({ maxPerStock: num(e.target.value, 15) / 100 })} />
        </label>
        <label className="text-sm font-medium">
          Most trades a month
          <input className={input} type="number" min={0} max={1000} value={r.maxTradesPerMonth} onChange={(e) => set({ maxTradesPerMonth: num(e.target.value, DEFAULT_RULES.maxTradesPerMonth) })} />
        </label>
        <label className="text-sm font-medium">
          Smallest order (€)
          <input className={input} type="number" min={0} step={50} value={r.minOrderEur} onChange={(e) => set({ minOrderEur: num(e.target.value, DEFAULT_RULES.minOrderEur) })} />
        </label>
        <label className="text-sm font-medium">
          Cool-off after big moves (hours)
          <input className={input} type="number" min={0} max={720} value={r.coolingHours} onChange={(e) => set({ coolingHours: num(e.target.value, DEFAULT_RULES.coolingHours) })} />
        </label>
        <label className="text-sm font-medium">
          No buys this many days before earnings
          <input className={input} type="number" min={0} max={30} value={r.noEarningsWithinDays} onChange={(e) => set({ noEarningsWithinDays: num(e.target.value, DEFAULT_RULES.noEarningsWithinDays) })} />
        </label>
      </div>
      <label className="mt-3 flex min-h-11 items-center gap-2 text-sm">
        <input type="checkbox" className="size-6 accent-teal-700" checked={r.onlyZero} onChange={(e) => set({ onlyZero: e.target.checked })} />
        Only stocks I can buy on finanzen.net zero
      </label>
      <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Defaults: orders of 500 € or more (free on finanzen.net zero), at most 15% in one stock and 10 stocks, 4 trades a month, a 24-hour cool-off.</p>
    </Card>
  )
}
