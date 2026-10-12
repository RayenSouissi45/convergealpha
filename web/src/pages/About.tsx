import { Card, PageHeader } from '../components/ui'

const LABELS: { label: string; meaning: string }[] = [
  { label: 'STRONG BUY — TOP CONVICTION', meaning: 'Rare. Almost all independent evidence agrees, and similar past setups were higher after 6 months at least 65% of the time (lower end of the 95% range).' },
  { label: 'BUY', meaning: 'Passes all 12 trade rules: fresh data, agreement between independent evidence, calibrated odds, positive expected value after costs, liquidity and no blocking event.' },
  { label: 'WATCH', meaning: 'Misses exactly one evidence rule by a small margin.' },
  { label: 'HOLD', meaning: 'A stock you own where no exit rule has triggered.' },
  { label: 'ROTATE', meaning: 'A holding that has lagged its own forecast for a month while a clearly faster candidate exists (after costs).' },
  { label: 'SELL / RISK WARNING', meaning: 'An exit rule fired, a blocking event appeared, the data failed, or the evidence decayed.' },
  { label: 'NO TRADE', meaning: 'The default. The evidence is not strong enough.' },
]

const FAMILIES: { name: string; text: string }[] = [
  { name: 'F1 Opinion', text: 'Analyst consensus, price targets and rating platforms, weighted by how well each source has actually predicted, and counted only for what they add beyond revisions and momentum.' },
  { name: 'F2 Revisions', text: 'How earnings estimates have moved over the last 60 days, and how many analysts raised vs cut.' },
  { name: 'F3 Earnings events', text: 'Size of earnings and revenue surprises, and guidance changes.' },
  { name: 'F4 Insiders and owners', text: 'Opportunistic open-market insider purchases (routine and pre-planned trades ignored) and institutional accumulation.' },
  { name: 'F5 Price and trend', text: 'Stock-specific momentum after removing the market and sector, industry momentum and trend.' },
  { name: 'F6 Quality and value', text: 'Profitability, cash flow, accruals and debt from SEC filings, as first reported.' },
  { name: 'F7 Context', text: 'Market regime, events, liquidity, crowding, implied volatility and news. It never votes for a trade; it can only block or shrink one.' },
]

const repoUrl = import.meta.env.VITE_REPO_URL

export default function About() {
  return (
    <>
      <PageHeader title="About & method" subtitle="What this site does, and what it cannot do." />
      <div className="space-y-4">
        <Card title="The honesty principle">
          <p className="text-sm leading-relaxed">
            No tool can make a stock rise for sure. ConvergeAlpha’s job is to put the odds in your
            favour, show exactly what each percentage promises, and say <strong>NO TRADE</strong>{' '}
            when the evidence is weak. This is a personal research tool, <strong>not financial advice</strong>.
          </p>
        </Card>

        <Card title="Research mode">
          <div className="space-y-2 text-sm leading-relaxed">
            <p>
              Every probability starts in <strong>RESEARCH MODE — not yet validated</strong>. It
              leaves research mode only for the horizons and labels that pass the validation lab:
              a walk-forward backtest with a holdout period run once, beating the S&P 500 and every
              simple baseline after costs, with well-calibrated probabilities.
            </p>
            <p>
              A missing value is always shown as “—”. Tap it to see why it is missing. The site
              never fills gaps with made-up numbers.
            </p>
          </div>
        </Card>

        <Card title="What a percentage promises">
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            <li>
              <strong>Horizon</strong>: 1 week, 1 month, 3 months or 6 months (5, 21, 63 or 126
              trading days).
            </li>
            <li>
              <strong>“Up”</strong> means the price is higher at the horizon.{' '}
              <strong>“Beat the market”</strong> means it did better than the S&P 500 over the same
              days — a different, harder promise.
            </li>
            <li>
              <strong>Sample size and range</strong>: odds come with how many similar past cases
              they rest on and a 95% range, in the form “Historically X% of N similar setups were
              higher after 6 months (low–high%)”.
            </li>
            <li>
              <strong>Validated or not</strong>: every percentage says whether it has passed the
              validation lab.
            </li>
          </ul>
        </Card>

        <Card title="Labels">
          <dl className="divide-y divide-slate-100 dark:divide-zinc-800">
            {LABELS.map((l) => (
              <div key={l.label} className="py-2.5">
                <dt className="text-sm font-semibold">{l.label}</dt>
                <dd className="mt-0.5 text-sm text-slate-600 dark:text-zinc-400">{l.meaning}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
            A label is always shown together with the exact numbers behind it. Position plans use a
            “planned exit level”, never a “maximum loss”: prices can gap past any level.
          </p>
        </Card>

        <Card title="Seven evidence families">
          <dl className="divide-y divide-slate-100 dark:divide-zinc-800">
            {FAMILIES.map((f) => (
              <div key={f.name} className="py-2.5">
                <dt className="text-sm font-semibold">{f.name}</dt>
                <dd className="mt-0.5 text-sm text-slate-600 dark:text-zinc-400">{f.text}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
            Each new source starts with zero weight and earns weight only if it adds value on data
            it has never seen, after costs. F1 and F2 have no point-in-time history before
            October 2026, so the models do not use them yet; they are shown as information.
            Backtested excess returns are halved before being shown, because free data mostly
            lacks delisted stocks.
          </p>
        </Card>

        <Card title="Data and privacy">
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            <li>Free, official sources and APIs only (SEC EDGAR, FINRA, FRED and others). No scraping of sites that forbid it.</li>
            <li>Every value keeps its source and publication time; nothing published after the 16:15 New York decision time is used for that day.</li>
            <li>No accounts, ads or tracking. Your portfolio and capital stay in this browser’s storage.</li>
          </ul>
          {repoUrl && (
            <a
              href={`${repoUrl}/blob/main/docs/METHODOLOGY.md`}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400"
            >
              Full methodology and formulas
            </a>
          )}
        </Card>
      </div>
    </>
  )
}
