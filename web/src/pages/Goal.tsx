import { lazy, Suspense, useDeferredValue, type ReactNode } from 'react'
import { Link } from 'react-router'
import { PlanTabs } from '../components/PlanTabs'
import { TaxSettings } from '../components/TaxSettings'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { WhenVisible } from '../components/WhenVisible'
import { formatEur } from '../lib/costs'
import { useSiteJson } from '../lib/data'
import { formatDay } from '../lib/format'
import { afterTax, chance, fan, monthlyNeeded, simulate, sustainableWithdrawal, type History, type Paths } from '../lib/goal'
import { reviewDue, useGoalSettings, type GoalSettings } from '../lib/goalSettings'
import { taxFrom, useTradeSettings } from '../lib/settings'

const GoalChart = lazy(() => import('../components/GoalChart'))

const input = 'mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-zinc-600 dark:bg-zinc-800'
const pct = (x: number) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : '—')
const eur0 = (x: number) => (Number.isFinite(x) ? formatEur(x, 0) : '—')

// Simulations are kept per set of inputs that change them (amounts do not: values are linear).
const cache = new Map<string, Paths>()
function paths(h: History, key: { years: number; stocks: number; ter: number; real: boolean; cautious: boolean }): Paths {
  const k = JSON.stringify(key)
  const hit = cache.get(k)
  if (hit) return hit
  const p = simulate(h, key)
  if (cache.size > 12) cache.clear()
  cache.set(k, p)
  return p
}

function Field({ id, label, help, children }: { id: string; label: string; help?: string; children: ReactNode }) {
  return (
    <div className="text-sm font-medium">
      <span className="flex items-center gap-1">
        <label htmlFor={id}>{label}</label>
        {help && (
          <Tip content={help} label={`About: ${label}`} className="no-underline">
            <span aria-hidden="true" className="inline-flex size-5 items-center justify-center rounded-full border border-slate-300 text-xs text-slate-600 dark:border-zinc-600 dark:text-zinc-400">?</span>
          </Tip>
        )}
      </span>
      {children}
    </div>
  )
}

function Inputs({ g, set }: { g: GoalSettings; set: (p: Partial<GoalSettings>) => void }) {
  const n = (v: string) => (Number.isFinite(Number(v)) ? Number(v) : 0)
  return (
    <Card title="Your plan">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="goal-have" label="Money you have now (€)">
          <input id="goal-have" className={input} type="number" inputMode="decimal" min={0} step={100} value={g.have} onChange={(e) => set({ have: n(e.target.value) })} />
        </Field>
        <Field id="goal-emergency" label="Keep as emergency cash (€)" help="Money for surprises stays out of the market: a common cushion is 3 to 6 months of your spending. It is not invested here.">
          <input id="goal-emergency" className={input} type="number" inputMode="decimal" min={0} step={100} value={g.emergency} onChange={(e) => set({ emergency: n(e.target.value) })} />
        </Field>
        <Field id="goal-monthly" label="Every month (€)" help="Added at the start of each month, like a savings plan. finanzen.net zero offers free ETF savings plans from 1 €.">
          <input id="goal-monthly" className={input} type="number" inputMode="decimal" min={0} step={10} value={g.monthly} onChange={(e) => set({ monthly: n(e.target.value) })} />
        </Field>
        <Field id="goal-goal" label="Your goal (€, 0 = none)" help="The amount you want to have at the end, in today's euros when 'today's euros' is on.">
          <input id="goal-goal" className={input} type="number" inputMode="decimal" min={0} step={1000} value={g.goal} onChange={(e) => set({ goal: n(e.target.value) })} />
        </Field>
        <Field id="goal-years" label={`Years: ${g.years}`}>
          <input id="goal-years" className="mt-2 w-full accent-teal-700" type="range" min={1} max={40} value={g.years} onChange={(e) => set({ years: n(e.target.value) })} />
        </Field>
        <Field id="goal-stocks" label={`In stocks: ${g.stocksPct}% (the rest in safe interest)`} help="Stocks = a broad stock ETF, modelled with the whole US stock market including dividends. The rest earns the 1-month Treasury bill rate, like a savings account.">
          <input id="goal-stocks" className="mt-2 w-full accent-teal-700" type="range" min={0} max={100} step={5} value={g.stocksPct} onChange={(e) => set({ stocksPct: n(e.target.value) })} />
        </Field>
        <Field id="goal-ter" label="Fund cost per year (%)" help="The ETF's yearly cost (TER), taken off every month. Broad ETFs usually cost 0.1% to 0.3%; check the fund's own page.">
          <input id="goal-ter" className={input} type="number" inputMode="decimal" min={0} max={3} step={0.05} value={g.terPct} onChange={(e) => set({ terPct: n(e.target.value) })} />
        </Field>
        <Field id="goal-payout" label="Years of withdrawals afterwards">
          <input id="goal-payout" className={input} type="number" inputMode="numeric" min={1} max={50} step={1} value={g.payoutYears} onChange={(e) => set({ payoutYears: n(e.target.value) })} />
        </Field>
      </div>
      <div className="mt-3 space-y-1">
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-6 accent-teal-700" checked={g.real} onChange={(e) => set({ real: e.target.checked })} />
          Show in today's euros (after inflation)
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-6 accent-teal-700" checked={g.cautious} onChange={(e) => set({ cautious: e.target.checked })} />
          Be cautious: stocks earn 2% a year less than in history
        </label>
        <TaxSettings />
      </div>
    </Card>
  )
}

export default function Goal() {
  const [g, set] = useGoalSettings()
  const [ts] = useTradeSettings()
  const d = useDeferredValue(g)
  const res = useSiteJson<History>('history.json')
  const header = (
    <>
      <PageHeader title="Plan" subtitle="What regular investing can grow into, replayed across about 100 years of real market history. Not a forecast." />
      <PlanTabs />
    </>
  )
  if (res.state !== 'ready') {
    return (
      <>
        {header}
        <Inputs g={g} set={set} />
        <Card className="mt-3">
          <p className="text-sm text-slate-600 dark:text-zinc-400">{res.state === 'loading' ? 'Loading market history…' : res.state === 'missing' ? 'The market history appears after the next daily update.' : `Could not load the market history (${res.message}).`}</p>
        </Card>
      </>
    )
  }
  const h = res.data
  const realOk = h.inflation.some((x) => x !== null && x !== undefined)
  const real = d.real && realOk
  const start = Math.max(0, d.have - d.emergency)
  const base = { years: d.years, ter: d.terPct / 100, real, cautious: d.cautious }
  const ps = paths(h, { ...base, stocks: d.stocksPct / 100 })
  const data = fan(ps, start, d.monthly)
  const last = data.at(-1)
  const goal = d.goal
  const c = chance(ps, start, d.monthly, goal)
  const need80 = monthlyNeeded(ps, start, goal, 0.8)
  const need50 = monthlyNeeded(ps, start, goal, 0.5)
  const nominal = real ? paths(h, { ...base, real: false, stocks: d.stocksPct / 100 }) : ps
  const nominalMiddle = fan(nominal, start, d.monthly).at(-1)?.p50 ?? NaN
  const paidIn = start + d.monthly * 12 * d.years
  const taxed = afterTax(nominalMiddle, paidIn, taxFrom(ts))
  const payout = last ? sustainableWithdrawal(h, last.p50, d.payoutYears, { stocks: d.stocksPct / 100, ...base }) : NaN
  const compare = [
    { name: 'All in safe interest', ps: paths(h, { ...base, stocks: 0 }) },
    { name: `Your mix (${d.stocksPct}% stocks)`, ps },
    { name: 'All in stocks', ps: paths(h, { ...base, stocks: 1 }) },
  ].map((x) => ({ name: x.name, middle: fan(x.ps, start, d.monthly).at(-1)?.p50 ?? NaN, bad: fan(x.ps, start, d.monthly).at(-1)?.p10 ?? NaN, chance: chance(x.ps, start, d.monthly, goal) }))
  const unit = real ? "today's euros" : 'euros'
  const due = reviewDue(g)
  return (
    <>
      {header}
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="grid content-start gap-3">
          <Inputs g={g} set={set} />
          {d.emergency > 0 && d.emergency > d.have && <p className="text-sm text-red-700 dark:text-red-400">Your emergency cash is more than the money you have: nothing is invested now.</p>}
        </div>
        <div className="grid content-start gap-3">
          <Card>
            {goal > 0 ? (
              <>
                <p className="text-sm text-slate-600 dark:text-zinc-400">Chance of reaching {formatEur(goal, 0)} ({unit}) in {d.years} years</p>
                <p className="text-4xl font-semibold tabular-nums" data-testid="goal-chance">{pct(c)}</p>
                <p className="mt-1 text-sm">
                  For 8 in 10 futures: <strong className="tabular-nums">{eur0(need80)} a month</strong> · for half of them: {eur0(need50)} a month
                </p>
              </>
            ) : (
              <p className="text-sm">Set a goal to see your chance of reaching it.</p>
            )}
            {last && (
              <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-sm dark:border-zinc-800">
                <div>
                  <dt className="text-xs text-slate-600 dark:text-zinc-400">Bad case (1 in 10)</dt>
                  <dd className="font-semibold tabular-nums">{eur0(last.p10)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600 dark:text-zinc-400">Middle</dt>
                  <dd className="font-semibold tabular-nums">{eur0(last.p50)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600 dark:text-zinc-400">Good case (1 in 10)</dt>
                  <dd className="font-semibold tabular-nums">{eur0(last.p90)}</dd>
                </div>
              </dl>
            )}
            <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
              You pay in {formatEur(paidIn, 0)}. Middle outcome after German tax when you sell: about {eur0(taxed)} in euros of that year (30% of an equity ETF's gain is tax free; {formatEur(taxFrom(ts).allowanceLeft, 0)} allowance).
            </p>
          </Card>
          {goal > 0 && (
            <Card title="Small changes, big effect">
              <ul className="space-y-1 text-sm" aria-label="What if">
                {[10, 25, 50].map((x) => (
                  <li key={x} className="flex justify-between gap-3 tabular-nums">
                    <span>+{formatEur(x, 0)} a month</span>
                    <span>{pct(chance(ps, start, d.monthly + x, goal))} chance</span>
                  </li>
                ))}
                <li className="flex justify-between gap-3 tabular-nums">
                  <span>+2 years</span>
                  <span>{pct(chance(paths(h, { ...base, years: d.years + 2, stocks: d.stocksPct / 100 }), start, d.monthly, goal))} chance</span>
                </li>
              </ul>
            </Card>
          )}
        </div>
      </div>
      <Card title={`How the money could grow (${unit})`} className="mt-3">
        <WhenVisible height="h-72">
          <Suspense fallback={<div className="h-72" aria-busy="true" />}>
            <GoalChart data={data} goal={goal} real={real} />
          </Suspense>
        </WhenVisible>
        <details className="mt-2 text-sm">
          <summary className="min-h-11 cursor-pointer content-center font-medium text-teal-700 dark:text-teal-400">Show as a table</summary>
          <table className="w-full text-right text-sm tabular-nums">
            <thead>
              <tr className="text-xs text-slate-600 dark:text-zinc-400">
                <th className="text-left font-medium">After</th>
                <th className="font-medium">Paid in{real ? ' (not adjusted)' : ''}</th>
                <th className="font-medium">Bad (1 in 10)</th>
                <th className="font-medium">Middle</th>
                <th className="font-medium">Good (1 in 10)</th>
              </tr>
            </thead>
            <tbody>
              {data.filter((r) => r.year > 0 && (r.year % 5 === 0 || r.year === d.years || r.year === 1)).map((r) => (
                <tr key={r.year} className="border-t border-slate-100 dark:border-zinc-800">
                  <td className="py-1 text-left">{r.year} y</td>
                  <td>{eur0(r.paidIn)}</td>
                  <td>{eur0(r.p10)}</td>
                  <td>{eur0(r.p50)}</td>
                  <td>{eur0(r.p90)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </Card>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card title="Your mix against simpler choices">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-xs text-slate-600 dark:text-zinc-400">
                <th className="text-left font-medium">Same money, same years</th>
                <th className="pl-3 text-right font-medium">Middle</th>
                <th className="pl-3 text-right font-medium">Bad (1 in 10)</th>
                {goal > 0 && <th className="pl-3 text-right font-medium">Goal</th>}
              </tr>
            </thead>
            <tbody>
              {compare.map((r) => (
                <tr key={r.name} className="border-t border-slate-100 dark:border-zinc-800">
                  <td className="py-1.5 text-left">{r.name}</td>
                  <td className="pl-3 text-right">{eur0(r.middle)}</td>
                  <td className="pl-3 text-right">{eur0(r.bad)}</td>
                  {goal > 0 && <td className="pl-3 text-right">{pct(r.chance)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">More stocks: a higher middle and a deeper bad case. Over short periods safe interest often wins; over long periods stocks usually did.</p>
        </Card>
        <Card title="Taking money out afterwards">
          <p className="text-sm">
            From the middle outcome ({eur0(last?.p50 ?? NaN)}), about <strong className="tabular-nums">{eur0(payout)} a month</strong> lasted {d.payoutYears} years in 9 of 10 futures ({unit}, same mix).
          </p>
          <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400">Bad years right at the start of withdrawals hurt most (sequence risk); that is included.</p>
        </Card>
      </div>
      <Card className="mt-3">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => set({ savedOn: new Date().toISOString().slice(0, 10), savedChance: Number.isFinite(c) ? c : null })} className="inline-flex min-h-11 items-center rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 dark:bg-teal-600 dark:hover:bg-teal-500">
            Save this plan
          </button>
          {g.savedOn && (
            <span className="text-sm text-slate-600 dark:text-zinc-400">
              Saved {formatDay(g.savedOn)}
              {g.savedChance !== null ? ` with a ${pct(g.savedChance)} chance` : ''}. {due ? <Badge tone="warn">A year has passed: review it</Badge> : 'Review it once a year or when your goal changes.'}
            </span>
          )}
        </div>
      </Card>
      <details className="mt-3 rounded-xl border border-slate-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
        <summary className="min-h-12 cursor-pointer content-center font-semibold">How this works and its limits</summary>
        <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700 dark:text-zinc-300">
          <li>Each of 4,000 futures strings together random 12-month stretches of real history ({ps.span}), so crashes, recoveries and long bad years keep their real shape. It shows how the same plan would have turned out, not what will happen.</li>
          <li>Stocks are the whole US stock market including dividends, in dollars, standing in for a broad world ETF in euros: currency swings and today's prices can make the future better or worse than history. "Be cautious" removes 2% a year.</li>
          <li>Safe interest = 1-month US Treasury bills. Inflation = US consumer prices. The fund cost is taken off every month; buying through a free savings plan costs no fee.</li>
          <li>Tax: German rules ({taxFrom(ts).filing === 'joint' ? 'couple' : 'single'}), counted when you sell at the end; the yearly advance tax on funds is paid along the way and credited then.</li>
          <li>
            Examples of broad, low-cost stock ETFs (check the costs and that your broker offers them): iShares Core MSCI World (IE00B4L5Y983), Vanguard FTSE All-World (IE00BK5BQT80), Xtrackers MSCI World (IE00BJ0KDQ92). Not advice.
          </li>
          <li>
            Data: {h.source ?? 'Kenneth R. French Data Library'}. <Link to="/columns" className="text-teal-700 underline dark:text-teal-400">Columns explained</Link>
          </li>
        </ul>
      </details>
    </>
  )
}
