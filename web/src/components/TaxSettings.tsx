import { formatEur } from '../lib/costs'
import { formatDay, formatPctAbs } from '../lib/format'
import { taxFrom, useTradeSettings } from '../lib/settings'
import { effectiveRate, TAX_RULES, type ChurchRate } from '../lib/taxes'

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'

/** Your German tax profile, remembered in this browser only. */
export function TaxSettings() {
  const [s, set] = useTradeSettings()
  const p = taxFrom(s)
  const max = TAX_RULES.allowance[p.filing]
  return (
    <details className="rounded-lg border border-slate-200 p-3 dark:border-zinc-700">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-medium">
        Taxes: {formatPctAbs(effectiveRate(p.church), 2)} on gains, {formatEur(p.allowanceLeft, 0)} allowance left this year
      </summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-slate-600 dark:text-zinc-400">
          Filing
          <select className={input} value={p.filing} onChange={(e) => set({ taxFiling: e.target.value === 'joint' ? 'joint' : 'single', allowanceLeft: TAX_RULES.allowance[e.target.value === 'joint' ? 'joint' : 'single'] })}>
            <option value="single">Single ({formatEur(TAX_RULES.allowance.single, 0)} allowance)</option>
            <option value="joint">Couple filing together ({formatEur(TAX_RULES.allowance.joint, 0)})</option>
          </select>
        </label>
        <label className="text-xs text-slate-600 dark:text-zinc-400">
          Church tax
          <select className={input} value={String(p.church)} onChange={(e) => set({ taxChurch: Number(e.target.value) as ChurchRate })}>
            <option value="0">None</option>
            <option value="0.08">8% (Bavaria, Baden-Württemberg)</option>
            <option value="0.09">9% (other states)</option>
          </select>
        </label>
        <label className="text-xs text-slate-600 dark:text-zinc-400">
          Allowance left this year (€)
          <input type="number" inputMode="decimal" min={0} max={max} step={50} value={p.allowanceLeft} onChange={(e) => set({ allowanceLeft: Number(e.target.value) })} className={input} />
        </label>
      </div>
      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
        German rules {TAX_RULES.version}, checked {formatDay(TAX_RULES.checked)}: 25% tax plus 5.5% solidarity surcharge on it (and church tax if you pay it) on gains and dividends above the allowance. Losses on stocks only offset gains on stocks. Not tax advice: your bank's yearly tax statement is the official number.
      </p>
    </details>
  )
}
