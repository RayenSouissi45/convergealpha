import { Link } from 'react-router'
import { useSiteJson } from '../lib/data'
import { formatDay, formatNum, formatPct, formatPctAbs, signClass } from '../lib/format'
import type { MarketFile } from '../types'
import { Missing } from './Missing'
import { Tip } from './Tip'
import { Badge, Card, Row, type Tone } from './ui'

const REGIME_TONE: Record<string, Tone> = { Normal: 'good', Caution: 'warn', Stress: 'bad' }

export function MarketCard() {
  const res = useSiteJson<MarketFile>('market.json')
  if (res.state !== 'ready') {
    return (
      <Card title="Market">
        <p className="text-sm text-slate-500 dark:text-zinc-400">
          {res.state === 'loading' ? 'Loading…' : 'Market data appears after the first daily pipeline run.'}
        </p>
      </Card>
    )
  }
  const m = res.data
  const spx = m.benchmarks['^GSPC']
  const vix = m.benchmarks['^VIX']
  const vs200 = spx?.price && spx.sma200 ? spx.price / spx.sma200 - 1 : null
  const regime = m.regime
  return (
    <Card
      title={`Market · ${formatDay(m.as_of)}`}
      aside={
        regime ? (
          <Tip content={`Regime rules: Normal = S&P 500 above its 200-day average and VIX below 25. Stress = below the 200-day average and VIX at least 30 (no new buys). Caution = anything in between, or the high-yield spread up more than 1 point in 3 months. Today: ${regime.reasons.join('; ')}.`} label={`Market regime ${regime.state}`} className="no-underline">
            <Badge tone={REGIME_TONE[regime.state] ?? 'neutral'}>Regime: {regime.state}</Badge>
          </Tip>
        ) : (
          <span className="text-sm">
            Regime: <Missing reason="The regime also needs the high-yield credit spread from FRED; connected in build phase 2." />
          </span>
        )
      }
    >
      <dl>
        <Row label="S&P 500">
          {spx?.price ? formatNum(spx.price) : '—'}{' '}
          {spx?.change_1d != null && <span className={signClass(spx.change_1d)}>({formatPct(spx.change_1d, 2)})</span>}
        </Row>
        <Row label={<Tip content="How far the S&P 500 is above (+) or below (−) its average close of the last 200 trading days. Below it is a warning sign.">vs 200-day average</Tip>}>
          {vs200 !== null ? <span className={signClass(vs200)}>{formatPct(vs200)}</span> : '—'}
        </Row>
        <Row label={<Tip content="CBOE Volatility Index: the market's expected volatility for the next 30 days. Above 25 is elevated, above 30 is stress.">VIX</Tip>}>
          {vix?.price ? formatNum(vix.price) : '—'}
        </Row>
        {m.macro?.BAMLH0A0HYM2 && (
          <Row label={<Tip content="Extra yield investors demand to hold junk bonds (FRED: BAMLH0A0HYM2). A rise of more than 1 point in 3 months puts the market in Caution.">High-yield credit spread</Tip>}>
            {m.macro.BAMLH0A0HYM2.value.toFixed(2)} pts{' '}
            <span className={`text-xs ${signClass(-m.macro.BAMLH0A0HYM2.change_3m)}`}>({m.macro.BAMLH0A0HYM2.change_3m >= 0 ? '+' : '−'}{Math.abs(m.macro.BAMLH0A0HYM2.change_3m).toFixed(2)} in 3m)</span>
          </Row>
        )}
        {m.macro?.T10Y2Y && <Row label={<Tip content="10-year minus 2-year Treasury yield (FRED). Negative = inverted curve.">Yield curve (10y − 2y)</Tip>}>{m.macro.T10Y2Y.value.toFixed(2)} pts</Row>}
        {m.breadth && (
          <>
            <Row label="Stocks up on the day">{formatPctAbs(m.breadth.advancing_pct, 0)}</Row>
            <Row label="Stocks above their 200-day average">{formatPctAbs(m.breadth.above_200d_pct, 0)}</Row>
          </>
        )}
      </dl>
      <Link to="/screener" className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
        Browse all {m.breadth ? m.breadth.stocks.toLocaleString('en-US') : ''} stocks
      </Link>
    </Card>
  )
}
