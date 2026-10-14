import { formatEur, ZERO_FEES, ZERO_FEES_CHECKED } from '../lib/costs'
import { formatDay } from '../lib/format'
import { feeText, useTradeSettings } from '../lib/settings'

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'

/** Fee rule, fractional shares: the costs every euro number uses, remembered in this browser. */
export function FeeSettings() {
  const [s, set] = useTradeSettings()
  return (
    <details className="rounded-lg border border-slate-200 p-3 dark:border-zinc-700">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-medium">Costs: {feeText(s)}</summary>
      <fieldset className="mt-2 space-y-1 text-sm">
        <legend className="sr-only">Fee rule</legend>
        <label className="flex min-h-11 items-start gap-2">
          <input type="radio" name="fee-rule" className="mt-1 size-5 accent-teal-700" checked={s.feeRule === 'zero'} onChange={() => set({ feeRule: 'zero' })} />
          <span>
            finanzen.net zero: 0 € for orders of {formatEur(ZERO_FEES.freeFrom ?? 500, 0)} or more, {formatEur(ZERO_FEES.buy)} below
            <span className="block text-xs text-slate-500 dark:text-zinc-400">Checked on {formatDay(ZERO_FEES_CHECKED)}. Fees change: check the broker's current price list.</span>
          </span>
        </label>
        <label className="flex min-h-11 items-center gap-2">
          <input type="radio" name="fee-rule" className="size-5 accent-teal-700" checked={s.feeRule === 'custom'} onChange={() => set({ feeRule: 'custom' })} />
          My own flat fee
        </label>
      </fieldset>
      {s.feeRule === 'custom' && (
        <div className="mt-1 grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-600 dark:text-zinc-400">
            Fee per buy (€)
            <input type="number" inputMode="decimal" min={0} step={0.5} value={s.feeBuy} onChange={(e) => set({ feeBuy: Number(e.target.value) })} className={input} />
          </label>
          <label className="text-xs text-slate-600 dark:text-zinc-400">
            Fee per sell (€)
            <input type="number" inputMode="decimal" min={0} step={0.5} value={s.feeSell} onChange={(e) => set({ feeSell: Number(e.target.value) })} className={input} />
          </label>
        </div>
      )}
      <label className="mt-2 flex min-h-11 items-center gap-2 text-sm">
        <input type="checkbox" className="size-6 accent-teal-700" checked={s.fractional} onChange={(e) => set({ fractional: e.target.checked })} />
        Fractional shares (simulation only)
      </label>
    </details>
  )
}
