import { Card, PageHeader } from '../components/ui'
import { Tip } from '../components/Tip'
import { useSiteJson } from '../lib/data'
import { formatPct } from '../lib/format'

interface RaceFile {
  live: { months: number; strategies: Record<string, { cumulative: number; months: number; max_drawdown: number; points: { date: string; excess: number }[] }> }
  backtest: Record<string, { years: number[]; strategies: Record<string, { net_excess_annual: number | null; t_stat: number; max_drawdown: number }> }> | null
  holdout: { strategies: Record<string, { net_excess_annual: number | null; t_stat: number; max_drawdown: number }> } | null
}

const NAMES: Record<string, string> = {
  app: 'App (model rank)',
  app_meta: 'App + meta-model',
  baseline_momentum: 'Momentum only',
  baseline_family_average: 'Equal-weight family average',
  baseline_all_eligible: 'All eligible stocks',
}

export default function BaselineRace() {
  const res = useSiteJson<RaceFile>('race.json')
  if (res.state !== 'ready') {
    return (
      <>
        <PageHeader title="Baseline race" subtitle="Does the app beat simple alternatives?" />
        <Card>
          <p className="text-sm text-slate-500">{res.state === 'loading' ? 'Loading…' : 'The race appears after the first daily build.'}</p>
        </Card>
      </>
    )
  }
  const { live, backtest, holdout } = res.data
  const periods: [string, Record<string, { net_excess_annual: number | null; t_stat: number; max_drawdown: number }>][] = [
    ...Object.entries(backtest ?? {}).map(([k, v]) => [`${k} (${v.years.join('–')})`, v.strategies] as [string, typeof v.strategies]),
    ...(holdout ? [['holdout (2024–mid 2026)', holdout.strategies] as [string, typeof holdout.strategies]] : []),
  ]
  const strategies = [...new Set(periods.flatMap(([, s]) => Object.keys(s)))]
  return (
    <>
      <PageHeader title="Baseline race" subtitle="The app against the S&P 500 and simple baselines, same rules and costs." />
      <div className="space-y-3">
        <Card title={<Tip content="Each month's first daily snapshot: the top 2% of eligible stocks by each method, held 21 trading days, compared with the S&P 500 after a 0.2% round-trip cost.">Live race</Tip>}>
          {live.months === 0 ? (
            <p className="text-sm text-slate-600 dark:text-zinc-400">The live race starts with the first monthly snapshot that has 21 trading days of results. It fills in month by month.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm dark:divide-zinc-800">
              {Object.entries(live.strategies).map(([k, v]) => (
                <li key={k} className="flex justify-between py-2">
                  <span>{k}</span>
                  <span className="tabular-nums">{formatPct(v.cumulative)} vs S&P · {v.months} months · max drawdown {formatPct(v.max_drawdown, 0)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Backtest race (net excess per year vs the S&P 500, halved)">
          {periods.length === 0 ? (
            <p className="text-sm text-slate-500">Appears after the first weekly validation run.</p>
          ) : (
            <div className="-mx-4 overflow-x-auto px-4">
              <table className="w-full min-w-max text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs text-slate-600 dark:border-zinc-700 dark:text-zinc-300">
                    <th className="px-2 py-1.5">Strategy</th>
                    {periods.map(([p]) => (
                      <th key={p} className="px-2 py-1.5">{p}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
                  <tr>
                    <th scope="row" className="px-2 py-1.5 text-left font-normal">S&P 500</th>
                    {periods.map(([p]) => (
                      <td key={p} className="px-2 py-1.5 tabular-nums">{formatPct(0)}</td>
                    ))}
                  </tr>
                  {strategies.map((s) => (
                    <tr key={s}>
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">{NAMES[s] ?? s}</th>
                      {periods.map(([p, st]) => {
                        const v = st[s]
                        return (
                          <td key={p} className="px-2 py-1.5 tabular-nums">
                            {v && v.net_excess_annual !== null ? `${formatPct(v.net_excess_annual * 0.5)} (t ${v.t_stat.toFixed(1)})` : '—'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-500">
            Revisions-only and third-party lists (Danelfin, Zacks, TipRanks…) are not in the race: there is no free point-in-time history of them. Backtested numbers are halved (survivorship haircut).
          </p>
        </Card>
      </div>
    </>
  )
}
