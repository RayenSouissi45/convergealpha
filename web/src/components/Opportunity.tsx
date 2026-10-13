import { useState } from 'react'
import { Link } from 'react-router'
import { formatDay, formatPct } from '../lib/format'
import { OPP_TEXT, useOpportunities } from '../lib/opportunity'
import type { OppColor, Opportunity } from '../types'
import { Icon } from './Icon'
import { Sheet } from './Sheet'
import { Badge } from './ui'

/** The badge pill (text always says what the colour means). */
export function OppPill({ color, compact = false }: { color: OppColor; compact?: boolean }) {
  return <Badge tone={OPP_TEXT[color].tone}>{compact ? OPP_TEXT[color].short : OPP_TEXT[color].title}</Badge>
}

/** Badge + "Why?" button that opens the explanation. `opp` is passed when it is already loaded
 * (stock page); otherwise opportunities.json is fetched when the panel opens. */
export function OppBadge({ ticker, color, opp, compact = false }: { ticker: string; color: OppColor; opp?: Opportunity | null; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="inline-flex items-center gap-1">
      <OppPill color={color} compact={compact} />
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen(true)
        }}
        className="inline-flex min-h-9 min-w-9 items-center justify-center rounded-md px-1.5 text-xs font-medium text-teal-700 underline underline-offset-2 dark:text-teal-400"
        aria-label={`Why is ${ticker} marked “${OPP_TEXT[color].title}”?`}
      >
        Why?
      </button>
      {open && <WhySheet ticker={ticker} color={color} opp={opp ?? null} onClose={() => setOpen(false)} />}
    </span>
  )
}

function WhySheet({ ticker, color, opp, onClose }: { ticker: string; color: OppColor; opp: Opportunity | null; onClose: () => void }) {
  const file = useOpportunities(!opp)
  const o = opp ?? (file.state === 'ready' ? (file.data.stocks[ticker] ?? null) : null)
  return (
    <Sheet open title={`${ticker}: ${OPP_TEXT[color].title}`} onClose={onClose}>
      {o ? (
        <OppWhy opp={o} />
      ) : (
        <p className="text-sm text-slate-600 dark:text-zinc-400">
          {file.state === 'loading' ? 'Loading…' : 'The explanation is not available (the daily build has not published it yet).'}
        </p>
      )}
      <Link to={`/stock/${encodeURIComponent(ticker)}`} className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400" onClick={onClose}>
        Open the {ticker} stock page
      </Link>
    </Sheet>
  )
}

function historyText(h: NonNullable<Opportunity['events'][number]['history']>): string {
  const who = h.scope === 'stock' ? 'this stock' : 'stocks in its industry'
  return `${h.n} past cases for ${who} (“${h.pattern}”): it went up ${Math.round(h.up_rate * 100)}% of the time over the next ${h.window}, ${formatPct(h.mean_return)} on average (${formatPct(h.mean_excess)} versus its usual move in those years).`
}

/** The "Why?" panel in plain English: what happened, what history says, what is missing or risky. */
export function OppWhy({ opp }: { opp: Opportunity }) {
  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <div className="flex flex-wrap items-center gap-2">
        <OppPill color={opp.color} />
        <span className="text-xs text-slate-500 dark:text-zinc-400">as of {formatDay(opp.as_of)}</span>
      </div>
      <p>{opp.summary}</p>
      {opp.events.length > 0 && (
        <section>
          <h3 className="font-semibold">What happened</h3>
          <ul className="mt-1 space-y-3">
            {opp.events.map((e, i) => (
              <li key={i} className="rounded-lg border border-slate-200 p-2.5 dark:border-zinc-700">
                <p>
                  <span className="font-medium">{formatDay(e.date)}:</span> {e.text}.
                </p>
                <p className="text-xs text-slate-600 dark:text-zinc-400">
                  Source:{' '}
                  {e.url ? (
                    <a href={e.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 underline">
                      {e.source}
                      <Icon name="external" className="size-3" />
                    </a>
                  ) : (
                    e.source
                  )}
                </p>
                <p className="mt-1.5">
                  <span className="font-medium">What history says: </span>
                  {e.history ? (
                    <>
                      {historyText(e.history)}{' '}
                      {e.history.passed ? (
                        <Badge tone={e.history.mean_excess > 0 ? 'good' : 'bad'}>Luck test passed{e.history.mean_excess > 0 ? '' : ' (points down)'}</Badge>
                      ) : (
                        <Badge tone="neutral">Luck test not passed</Badge>
                      )}
                    </>
                  ) : (
                    <span className="text-slate-600 dark:text-zinc-400">{e.history_note}</span>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {opp.checks.length > 0 && (
        <section>
          <h3 className="font-semibold">The checks for “confirmed”</h3>
          <ul className="mt-1 space-y-1">
            {opp.checks.map((c) => (
              <li key={c.text} className="flex gap-2">
                <span aria-hidden="true" className={c.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}>
                  {c.ok ? '✓' : '✗'}
                </span>
                <span>
                  <span className="sr-only">{c.ok ? 'Passed: ' : 'Not passed: '}</span>
                  {c.text}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {(opp.missing.length > 0 || opp.risks.length > 0) && (
        <section>
          <h3 className="font-semibold">What is missing or risky</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {[...opp.risks, ...opp.missing].map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-xs text-slate-500 dark:text-zinc-400">
        Never green on news alone. Even a confirmed opportunity can fail: the badge says the odds look better than usual, not that the price will rise.
      </p>
    </div>
  )
}
