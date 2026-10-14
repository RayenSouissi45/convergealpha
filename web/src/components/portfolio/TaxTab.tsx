import { useState } from 'react'
import { formatEur, formatEurSigned } from '../../lib/costs'
import { harvestSaving, taxYears, type Journal, type Position } from '../../lib/journal'
import { taxFrom, useTradeSettings } from '../../lib/settings'
import { taxOnGain } from '../../lib/taxes'
import { TaxSettings } from '../TaxSettings'
import { Card } from '../ui'

export function TaxTab({ j, ps }: { j: Journal; ps: Position[] }) {
  const [settings] = useTradeSettings()
  const [now] = useState(() => new Date())
  const profile = taxFrom(settings)
  const years = taxYears(j, profile)
  const year = now.getFullYear()
  const cur = years.find((y) => y.year === year)
  const net = cur?.stockNet ?? 0
  const losers = ps.filter((p) => (p.gainEur ?? 0) < 0).map((p) => ({ p, saving: harvestSaving(net, p.gainEur ?? 0, profile) })).filter((x) => x.saving > 0)
  const winners = ps.filter((p) => (p.gainEur ?? 0) > 0).map((p) => ({ p, tax: taxOnGain(p.gainEur ?? 0, profile).tax }))
  const december = now.getMonth() >= 10
  return (
    <div className="grid gap-3">
      <TaxSettings />
      <Card title="Taxes by year (estimate)">
        {years.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-zinc-400">Nothing sold and no dividends logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm tabular-nums">
              <thead>
                <tr className="text-xs text-slate-600 dark:text-zinc-400">
                  <th className="text-left font-medium">Year</th>
                  <th className="pl-3 font-medium">Stock gains</th>
                  <th className="pl-3 font-medium">Stock losses</th>
                  <th className="pl-3 font-medium">Dividends</th>
                  <th className="pl-3 font-medium">Allowance used</th>
                  <th className="pl-3 font-medium">Tax</th>
                  <th className="pl-3 font-medium">Loss carried</th>
                </tr>
              </thead>
              <tbody>
                {years.map((y) => (
                  <tr key={y.year} className="border-t border-slate-100 dark:border-zinc-800">
                    <td className="py-1.5 text-left">{y.year}</td>
                    <td className="pl-3">{formatEur(y.stockGains, 0)}</td>
                    <td className="pl-3">{formatEur(y.stockLosses, 0)}</td>
                    <td className="pl-3">{formatEur(y.dividends, 0)}</td>
                    <td className="pl-3">{formatEur(y.allowanceUsed, 0)}</td>
                    <td className="pl-3 font-semibold">{formatEur(y.estimatedTax, 0)}</td>
                    <td className="pl-3">{formatEur(y.lossCarry, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Stock losses only offset stock gains (and carry over to next year). The US tax on dividends counts toward the German tax. Your bank's yearly tax statement is the official number; the CSV export in the Journal tab helps you check it.</p>
      </Card>
      <Card title={december ? 'Before the year ends' : 'Selling a loser to save tax'}>
        {losers.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-zinc-400">Nothing to do: {net > 0 ? 'no open losses to set against this year’s gains' : 'no net stock gains this year to set losses against'}.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {losers.map(({ p, saving }) => (
              <li key={p.ticker}>
                Selling <strong>{p.ticker}</strong> ({formatEurSigned(p.gainEur ?? 0, 0)}) would save about <strong className="tabular-nums">{formatEur(saving, 0)}</strong> tax this year. Only if you would sell it anyway: tax should not decide on its own.
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Selling a winner now or later">
        {winners.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-zinc-400">No open gains.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {winners.map(({ p, tax }) => (
              <li key={p.ticker}>
                <strong>{p.ticker}</strong>: selling now costs about <strong className="tabular-nums">{formatEur(tax, 0)}</strong> tax{tax > 0 ? `; kept invested, that money keeps growing (about ${formatEur(tax * 0.07, 0)} a year at 7%)` : ' (inside your allowance)'}.
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
