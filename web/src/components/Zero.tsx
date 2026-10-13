import { formatInt } from '../lib/format'
import { listDateText, useBrokerList, useOnlyZero, zeroAvailability, zeroCounts } from '../lib/zero'
import type { Cell } from '../types'
import { Tip } from './Tip'

/** The tick box with its count ("1,234 of 2,461 stocks buyable"), or its disabled reason. */
export function ZeroToggle({ values, noun = 'stocks' }: { values: (Cell | undefined)[]; noun?: string }) {
  const [on, setOn] = useOnlyZero()
  const list = useBrokerList()
  const avail = zeroAvailability(list)
  const c = zeroCounts(values)
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
      <label className={`inline-flex min-h-11 items-center gap-2 ${avail.ok ? '' : 'text-slate-400 dark:text-zinc-500'}`}>
        <input
          type="checkbox"
          className="size-6 accent-teal-700"
          checked={on && avail.ok}
          disabled={!avail.ok}
          onChange={(e) => setOn(e.target.checked)}
          aria-describedby="zero-status"
        />
        Only stocks I can buy on finanzen.net zero
      </label>
      <span id="zero-status" className="text-xs text-slate-500 dark:text-zinc-400" aria-live="polite">
        {avail.ok
          ? `${formatInt(c.yes)} of ${formatInt(values.length)} ${noun} buyable${c.unknown ? ` · ${formatInt(c.unknown)} not sure (shown with ?)` : ''} · list dated ${listDateText(list)}`
          : avail.why}
      </span>
    </div>
  )
}

/** A small original badge (the app's own style, no broker branding). Inside links, pass
 * interactive={false}: the explanation is then in the title and for screen readers. */
export function ZeroBadge({ value, interactive = true }: { value: Cell | undefined; interactive?: boolean }) {
  const list = useBrokerList()
  if (value === false || !zeroAvailability(list).ok) return null
  const yes = value === true
  const text = yes
    ? `Available on finanzen.net zero (list dated ${listDateText(list)})`
    : 'Not sure if finanzen.net zero offers it: listed in the US less than 30 days ago, so the weekly list may not have it yet.'
  const pill = (
    <span
      className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 text-[10px] leading-4 font-semibold ring-1 ring-inset ${
        yes
          ? 'bg-teal-50 text-teal-800 ring-teal-600/30 dark:bg-teal-950 dark:text-teal-200 dark:ring-teal-400/30'
          : 'bg-slate-100 text-slate-600 ring-slate-400/30 dark:bg-zinc-800 dark:text-zinc-300'
      }`}
    >
      {yes ? (
        <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M2.5 6.5 5 9l4.5-6" />
        </svg>
      ) : null}
      {yes ? 'buyable' : '?'}
    </span>
  )
  if (!interactive) {
    return (
      <span title={text} className="inline-flex">
        {pill}
        <span className="sr-only">{text}</span>
      </span>
    )
  }
  return (
    <Tip content={text} label={text} className="no-underline">
      {pill}
    </Tip>
  )
}
