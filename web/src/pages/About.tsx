import { Link } from 'react-router'
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

        <Card title="How often was it right?">
          <div className="space-y-2 text-sm leading-relaxed">
            <p>
              A forecast says “58% chance up”. Is that honest? To check, the app looks back at its own
              past forecasts. It groups them by their chance (for example all forecasts between 55%
              and 58%) and counts how many of those stocks really went up.
            </p>
            <p>
              The stock page then says, for each horizon, for example: “When the app said about 57%,
              the stock was actually higher 54% of the time (20,626 cases, range 52.9%–54.3%).” If the two numbers are
              close, the app was honest for such stocks. If the second is much lower, it was too
              optimistic.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Only forecasts the models made before they saw the outcome are used (walk-forward, 2016–2023). The 2024–2026 holdout is never used for this.</li>
              <li>Each group has at least 200 past cases. The range is the 95% Wilson interval.</li>
              <li>The real uncertainty is wider than the range: cases overlap in time, and stocks move together.</li>
              <li>A ✓ means that horizon also passed the holdout test (2024–2026). Without it, the horizon is still in research mode.</li>
            </ul>
          </div>
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

        <Card title="Columns and picks">
          <p className="text-sm leading-relaxed">
            Every screener column is explained in plain English on{' '}
            <Link to="/columns" className="underline">Columns explained</Link>. The{' '}
            <Link to="/picks" className="underline">Picks</Link> page mixes safety, upside and
            confidence with weights fixed in advance; it is tracked live in the Baseline race.
          </p>
        </Card>

        <Card title="Costs in euros">
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            <li>finanzen.net zero sends orders to gettex. The app assumes 1 € per buy and 1 € per sell (change it on the Plan page; check your broker’s current price list).</li>
            <li>Example: you put in 100 €. 1 € goes to the fee, so you get 99 € of stock. Selling costs 1 € again. So the stock must rise about 2% just to give you your 100 € back. This “break-even move” is shown everywhere.</li>
            <li>On top, you pay a small spread (the gap between buying and selling prices), estimated from how much the stock trades each day.</li>
            <li>US prices are turned into euros with the European Central Bank’s daily EUR/USD rate (the first version of the strategies keeps FRED’s rate, its recorded rule). If the dollar falls, your US shares are worth fewer euros, even when the stock price does not move.</li>
            <li>Whole shares only, like at the broker: a 400 € share does not fit into 200 €. Money that is left over stays as cash.</li>
          </ul>
        </Card>

        <Card title="Plan, opportunities and strategies">
          <div className="space-y-2 text-sm leading-relaxed">
            <p>
              <Link to="/plan" className="font-semibold underline">Plan</Link>: you choose how safe, how much upside, how long and how much money. The app shows its three best fits and “split over the top two” with the shares you can buy, the fees, the break-even move, the chance of ending with more money after costs, how often similar forecasts were right, and a middle, bad and good result in euros. GREEN only when everything lines up; GREY means “waiting is a valid choice”.
            </p>
            <p>
              <strong>Opportunity badge</strong>: one badge joins the app’s event signals. GREEN “Confirmed opportunity” needs a fresh event (last 7 days) of a kind that passed the luck test in this stock’s history, at least 3 strong evidence families and a validated chance of rising above the usual rate. AMBER “Possible, not confirmed” = a fresh event without all of that. RED “Hype / be careful” = a big jump or loud news with weak evidence or a risk such as heavy short selling or a share offering. News alone is never green. Tap “Why?” for the plain explanation and the source.
            </p>
            <p>
              <Link to="/strategies" className="font-semibold underline">Strategies</Link>: five rule-based strategies with <strong>paper money</strong>: version 1 with 200 € each from 13 Oct 2026, and version 2 with 5,000 € each from 14 Oct 2026 (free orders from 500 €, the tested sell rule). Every trading day they decide after the close and trade at the next opening price, with fees, spread and euros, and they explain every buy, sell and hold. Each version races against the same money put into the S&P 500. Each strategy runs twice with the same rules: once only on stocks you can buy on finanzen.net zero (the version to copy) and once on all stocks, so you see what the broker’s list changes. Their rules were fixed before the start and are never tuned; a changed rule starts as a new version, and the older versions keep running unchanged. Every order is kept in a tamper-proof ledger. Paper money only: past and live results do not guarantee future results.
            </p>
          </div>
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
