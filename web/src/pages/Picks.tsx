import { Link, useSearchParams } from 'react-router'
import { LabelBadge } from '../components/LabelBadge'
import { Missing } from '../components/Missing'
import { Tip } from '../components/Tip'
import { Badge, Card, PageHeader } from '../components/ui'
import { chanceClass } from '../lib/cells'
import { H_LONG, H_SHORT, HORIZONS } from '../lib/columns'
import { useSiteJson } from '../lib/data'
import { formatDay, formatInt, formatPct, signClass } from '../lib/format'
import { useBrokerList, useOnlyZero, zeroAvailability } from '../lib/zero'
import { ZeroBadge, ZeroToggle } from '../components/Zero'
import type { Pick, PicksFile } from '../types'

type TabId = 'balanced' | 'safest' | 'upside' | 'likely'

const TABS: { id: TabId; label: string; help: string }[] = [
  { id: 'balanced', label: 'Balanced', help: 'Sorted by the average of Safety, Upside and Confidence.' },
  { id: 'safest', label: 'Safest', help: 'Sorted by Safety: low volatility, a smaller bad case, quality, no earnings soon.' },
  { id: 'upside', label: 'Most upside', help: 'Sorted by Upside: the expected 6-month change, and a little of the good case.' },
  { id: 'likely', label: 'Most likely to rise', help: 'Sorted by Confidence: the chance of rising and how often the app was right for that chance.' },
]

const SCORE_HELP = {
  safety: 'Safety, 0–100 within the sector: low volatility, a smaller bad case (10th percentile), quality family F6, and no earnings report in the next 5 trading days.',
  upside: 'Upside, 0–100 within the sector: the middle 6-month forecast, with a smaller weight on the good case (90th percentile).',
  confidence: 'Confidence, 0–100 within the sector: the chance of rising (validated P(up) 6m when available) and how often the app was right for that chance before.',
} as const

function ScoreBar({ id, label, value }: { id: keyof typeof SCORE_HELP; label: string; value: number | null }) {
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-1 text-xs">
        <Tip content={SCORE_HELP[id]}>{label}</Tip>
        <span className="font-semibold tabular-nums">{value === null ? '—' : Math.round(value)}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-zinc-800" role="img" aria-label={`${label} ${value === null ? 'not available' : `${Math.round(value)} out of 100`}`}>
        {value !== null && <div className="h-2 rounded-full" style={{ width: `${Math.max(3, value)}%`, background: 'var(--viz-series-1)' }} />}
      </div>
    </div>
  )
}

function HorizonGrid({ p }: { p: Pick }) {
  return (
    <table className="mt-3 w-full table-fixed text-xs tabular-nums">
      <caption className="sr-only">Forecast for {p.ticker} by horizon</caption>
      <thead>
        <tr className="text-slate-500 dark:text-zinc-400">
          <th scope="col" className="w-[30%] pb-1 text-left font-medium">
            <span className="sr-only">Measure</span>
          </th>
          {HORIZONS.map((h) => (
            <th key={h} scope="col" className="pb-1 text-right font-medium">
              <abbr title={H_LONG[h]} className="no-underline">{H_SHORT[h]}</abbr>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-zinc-800">
        <tr>
          <th scope="row" className="py-1 text-left font-normal">
            <Tip content="The middle forecast for the price change. Half of the outcomes are expected above it, half below.">Expected</Tip>
          </th>
          {HORIZONS.map((h) => {
            const v = p.horizons[h]?.median
            return (
              <td key={h} className={`py-1 text-right ${signClass(v)}`}>
                {v === null || v === undefined ? <Missing reason="No forecast." /> : formatPct(v)}
              </td>
            )
          })}
        </tr>
        <tr>
          <th scope="row" className="py-1 text-left font-normal">
            <Tip content="Chance the price (with dividends) is higher at the end of the period. A * means this horizon has not passed the validation lab (research mode).">Chance up</Tip>
          </th>
          {HORIZONS.map((h) => {
            const x = p.horizons[h]
            return (
              <td key={h} className={`py-1 text-right ${chanceClass(x?.p_up)}`}>
                {x?.p_up === null || x?.p_up === undefined ? <Missing reason="No forecast." /> : `${Math.round(x.p_up * 100)}%${x.validated ? '' : '*'}`}
              </td>
            )
          })}
        </tr>
        <tr>
          <th scope="row" className="py-1 text-left font-normal">
            <Tip content="How often this was right before: of the past cases where the app gave a similar chance, the share that really went up (2016–2023, out of sample). ± is the 95% range. ✓ = this horizon passed the holdout test.">Right before</Tip>
          </th>
          {HORIZONS.map((h) => {
            const x = p.horizons[h]
            const r = x?.reliability
            return (
              <td key={h} className="py-1 text-right align-top">
                {r ? (
                  <span title={`${Math.round(r.rate * 100)}% of ${r.n !== null ? formatInt(r.n) : '?'} similar past cases were higher after ${H_LONG[h]} (range ${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)}%).`}>
                    <span className={chanceClass(r.rate)}>{Math.round(r.rate * 100)}%</span>
                    <span className="block text-[10px] text-slate-500 dark:text-zinc-400">
                      ±{Math.max(1, Math.round(Math.max(r.rate - r.lo, r.hi - r.rate) * 100))} {x.validated ? '✓' : ''}
                    </span>
                  </span>
                ) : (
                  <Missing reason="No past record yet: it arrives with the weekly model run." />
                )}
              </td>
            )
          })}
        </tr>
      </tbody>
    </table>
  )
}

function PickCard({ p, place }: { p: Pick; place: number }) {
  return (
    <li className="min-w-0">
      <Card>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-xs font-semibold text-slate-500 tabular-nums dark:text-zinc-400">#{place}</span>
              <Link to={`/stock/${encodeURIComponent(p.ticker)}`} className="text-lg font-semibold text-teal-700 underline-offset-2 hover:underline dark:text-teal-400">
                {p.ticker}
              </Link>
              <ZeroBadge value={p.zero} />
            </div>
            <p className="truncate text-sm text-slate-600 dark:text-zinc-400" title={p.name ?? undefined}>
              {p.name ?? '—'}
            </p>
          </div>
          <LabelBadge label={p.label} />
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
          {p.sector ? `${p.sector} · ` : ''}Next earnings: {p.next_earnings ? formatDay(p.next_earnings) : 'no date known'}
          {p.zero === false ? ' · not on finanzen.net zero' : ''}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-3">
          <ScoreBar id="safety" label="Safety" value={p.scores.safety} />
          <ScoreBar id="upside" label="Upside" value={p.scores.upside} />
          <ScoreBar id="confidence" label="Confidence" value={p.scores.confidence} />
        </div>
        <HorizonGrid p={p} />
        <div className="mt-3 text-sm">
          <p className="font-medium">Why it is here</p>
          <ul className="mt-0.5 list-disc space-y-0.5 pl-5 text-slate-700 dark:text-zinc-300">
            {p.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="mt-2">
            <span className="font-medium">Main risk:</span> <span className="text-slate-700 dark:text-zinc-300">{p.risk}</span>
          </p>
        </div>
        <Link to={`/stock/${encodeURIComponent(p.ticker)}`} className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
          Open the {p.ticker} stock page
        </Link>
      </Card>
    </li>
  )
}

function RaceStatus({ race }: { race: PicksFile['race'] }) {
  if (race?.months) {
    return (
      <>
        Live since {race.since ? formatDay(`${race.since.slice(0, 4)}-${race.since.slice(4, 6)}-${race.since.slice(6, 8)}`) : 'its first day'}:{' '}
        <strong className={signClass(race.cumulative)}>{formatPct(race.cumulative ?? 0)}</strong> versus the S&P 500 after {race.months} month{race.months === 1 ? '' : 's'} (after costs).
      </>
    )
  }
  return (
    <>
      {race?.since
        ? `Tracked live since ${formatDay(`${race.since.slice(0, 4)}-${race.since.slice(4, 6)}-${race.since.slice(6, 8)}`)}.`
        : 'Live tracking starts with today’s picks.'}{' '}
      The first result comes 21 trading days later.
    </>
  )
}

export default function Picks() {
  const res = useSiteJson<PicksFile>('picks.json')
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id ?? 'balanced') as TabId
  const [onlyZero] = useOnlyZero()
  const zeroOk = zeroAvailability(useBrokerList()).ok

  const header = (
    <>
      <PageHeader title="Picks" subtitle="The app’s best-balanced suggestions: safety, upside and confidence together." />
      <div role="note" className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100">
        <strong>Research mode — these are the strongest-looking stocks by the app’s numbers, not guaranteed buys.</strong>{' '}
        The page keeps its research badge until this strategy beats the S&P 500 live in the{' '}
        <Link to="/baseline-race" className="underline">Baseline race</Link>.
      </div>
    </>
  )

  if (res.state !== 'ready') {
    return (
      <>
        {header}
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            {res.state === 'loading' ? 'Loading picks…' : res.state === 'missing' ? 'Picks appear after the next daily pipeline run.' : `Could not load the picks (${res.message}).`}
          </p>
        </Card>
      </>
    )
  }

  const file = res.data
  const useZero = onlyZero && zeroOk && !!file.tabs_zero
  const tickers = (useZero ? file.tabs_zero?.[tab] : file.tabs[tab]) ?? []
  const picks = tickers.map((t) => file.stocks[t]).filter((p): p is Pick => !!p)
  const all = (file.tabs[tab] ?? []).map((t) => file.stocks[t]?.zero ?? null)
  const s = file.summary
  const w = file.weights

  return (
    <>
      {header}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Tip content="Every percentage here is in research mode unless it says validated. Labels and picks have not passed the validation lab." className="no-underline">
          <Badge tone="warn">RESEARCH MODE — not yet validated</Badge>
        </Tip>
        <span className="text-xs text-slate-500 dark:text-zinc-400">
          Data as of {formatDay(file.as_of)} · <RaceStatus race={file.race} />
        </span>
      </div>
      <div role="tablist" aria-label="Pick lists" className="-mx-4 mb-2 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            title={t.help}
            onClick={() => setParams(t.id === 'balanced' ? {} : { tab: t.id }, { replace: true })}
            className={`min-h-11 shrink-0 rounded-full border px-3.5 text-sm font-medium whitespace-nowrap ${
              tab === t.id ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-600' : 'border-slate-300 bg-white dark:border-zinc-600 dark:bg-zinc-900'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="mb-1 text-sm text-slate-600 dark:text-zinc-400">{TABS.find((t) => t.id === tab)?.help} Top {file.top}; every pick scores at least {file.floor} on Safety, Upside and Confidence.</p>
      <div className="mb-3">
        <ZeroToggle values={all} noun="picks" />
      </div>
      {picks.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-600 dark:text-zinc-400">
            No stock passes every rule today ({formatInt(s.candidates)} candidates, none scores {file.floor}+ on all three). That is the app being careful, not an error.
          </p>
        </Card>
      ) : (
        <ol className="grid grid-cols-1 gap-3 lg:grid-cols-2" aria-label={`${TABS.find((t) => t.id === tab)?.label} picks`}>
          {picks.map((p, i) => (
            <PickCard key={p.ticker} p={p} place={i + 1} />
          ))}
        </ol>
      )}
      <Card title="How picks are chosen" className="mt-4">
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700 dark:text-zinc-300">
          <li>
            Only eligible stocks, without a SELL / RISK WARNING label, without a blocking event, and with a full forecast: {formatInt(s.candidates)} of {formatInt(s.eligible)} eligible stocks today ({formatInt(s.sell)} SELL, {formatInt(s.blocked)} blocked, {formatInt(s.no_forecast)} without a forecast).
          </li>
          <li>
            Each score is a percentile within the stock’s sector (0 = weakest, 100 = strongest; sectors with fewer than {file.min_sector} candidates are compared with all candidates).
          </li>
          <li>
            <strong>Confidence</strong> = {Math.round((w.confidence?.probability ?? 0) * 100)}% chance of rising ({s.probability_source}) + {Math.round((w.confidence?.reliability ?? 0) * 100)}% how often the app was right for that chance (lower end of the 95% range){s.reliability_available ? '' : '; the past record is not available yet, so only the chance counts'}.
          </li>
          <li>
            <strong>Upside</strong> = {Math.round((w.upside?.median_6m ?? 0) * 100)}% middle 6-month forecast + {Math.round((w.upside?.p90_6m ?? 0) * 100)}% good case (90th percentile).
          </li>
          <li>
            <strong>Safety</strong> = {Math.round((w.safety?.low_volatility ?? 0) * 100)}% low volatility + {Math.round((w.safety?.small_downside ?? 0) * 100)}% smaller bad case (10th percentile) + {Math.round((w.safety?.quality_f6 ?? 0) * 100)}% quality (F6) + {Math.round((w.safety?.no_earnings_5d ?? 0) * 100)}% no earnings in the next 5 trading days.
          </li>
          <li>
            <strong>Balanced</strong> = the average of the three. A pick needs at least {file.floor} on each, so it is never strong in one area and terrible in another. {formatInt(s.passing_floor)} stocks pass today.
          </li>
          <li>These weights were fixed in advance and are never tuned on past results.</li>
        </ul>
        <p className="mt-2 text-sm">
          <Link to="/columns" className="text-teal-700 underline dark:text-teal-400">Columns explained</Link> ·{' '}
          <Link to="/baseline-race" className="text-teal-700 underline dark:text-teal-400">Live tracking in the Baseline race</Link>
        </p>
      </Card>
    </>
  )
}
