import { PageHeader, Planned } from '../components/ui'

const PRESETS = [
  'Most likely to rise',
  'Biggest upside',
  'Fastest',
  'Safest',
  'Insider buying',
  'Analysts upgrading',
  'Earnings soon',
  'Avoid',
]

export default function Screener() {
  return (
    <>
      <PageHeader title="Screener" subtitle="Every US common stock, searchable and sortable." />
      <div className="space-y-3">
        <Planned title="All US stocks" phase={1}>
          <p>
            About 5,000–6,000 NYSE, Nasdaq and NYSE American common stocks (no ETFs, funds,
            warrants, units, preferreds or rights), with price, returns, volatility and trend,
            refreshed automatically after each US close.
          </p>
          <p>Stocks below the liquidity minimum will be shown greyed as “not eligible for signals”.</p>
        </Planned>
        <Planned title="Evidence and forecast columns" phase={3}>
          <p>
            Label, chance of being higher at 1 week / 1 month / 3 months / 6 months, expected gain
            per month, speed, the six evidence-family scores, analyst consensus and target upside,
            insider buying, short interest and data freshness.
          </p>
          <p>Presets: {PRESETS.join(' · ')}.</p>
        </Planned>
      </div>
    </>
  )
}
