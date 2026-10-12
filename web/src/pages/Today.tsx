import { Missing } from '../components/Missing'
import { Card, PageHeader, PhaseChip } from '../components/ui'

const SECTIONS: { title: string; phase: number; text: string }[] = [
  {
    title: 'Top Conviction',
    phase: 3,
    text: 'Shown only when almost all independent evidence agrees and similar past setups were higher after 6 months at least 65% of the time (Wilson lower bound). Expect this list to be empty most days.',
  },
  { title: 'Buy list, sorted by expected value', phase: 3, text: 'Stocks passing all 12 trade rules, with the numbers behind each label.' },
  { title: 'Most likely to rise', phase: 3, text: 'Ranked by the lower bound of the 6-month chance of being higher.' },
  { title: 'Biggest upside', phase: 2, text: 'Optimistic (90th percentile) 6-month forecast and analyst target upside.' },
  { title: 'Fastest', phase: 3, text: 'Expected gain per month divided by volatility, so money does not sit in slow stocks.' },
  { title: 'Insider buying this week', phase: 2, text: 'Opportunistic open-market purchases from SEC Form 4; routine and 10b5-1 plan trades are excluded.' },
  { title: 'Earnings this week', phase: 2, text: 'Upcoming reports, flagged when they block new entries.' },
  { title: 'Warnings for my holdings', phase: 3, text: 'SELL / RISK and ROTATE signals for the stocks in My portfolio.' },
]

export default function Today() {
  return (
    <>
      <PageHeader title="Today" subtitle="What to look at after today's close." />
      <Card className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm">
            <span className="text-slate-600 dark:text-zinc-400">Market regime: </span>
            <strong>
              <Missing reason="Needs the S&P 500 vs its 200-day average and the VIX (FRED). Connected in build phase 2." />
            </strong>
          </div>
          <PhaseChip phase={2} />
        </div>
      </Card>
      <ul className="space-y-3">
        {SECTIONS.map((s) => (
          <li key={s.title}>
            <Card title={s.title} aside={<PhaseChip phase={s.phase} />}>
              <p className="text-sm text-slate-600 dark:text-zinc-400">{s.text}</p>
            </Card>
          </li>
        ))}
      </ul>
    </>
  )
}
