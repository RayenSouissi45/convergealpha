// The interface is English, so formats are English too (in the viewer's own time zone).
const LOCALE = 'en-US'
const dateTime = new Intl.DateTimeFormat(LOCALE, { dateStyle: 'medium', timeStyle: 'short' })
const newYork = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'America/New_York',
  dateStyle: 'medium',
  timeStyle: 'short',
})
const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto', style: 'short' })
const day = new Intl.DateTimeFormat(LOCALE, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
const compact = new Intl.NumberFormat(LOCALE, { notation: 'compact', maximumFractionDigits: 1 })
const int = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}

export function formatNewYork(iso: string): string {
  return `${newYork.format(new Date(iso))} New York`
}

export function formatAge(iso: string, now: Date = new Date()): string {
  const seconds = (new Date(iso).getTime() - now.getTime()) / 1000
  const abs = Math.abs(seconds)
  if (abs < 60) return relative.format(Math.round(seconds), 'second')
  if (abs < 3600) return relative.format(Math.round(seconds / 60), 'minute')
  if (abs < 86400) return relative.format(Math.round(seconds / 3600), 'hour')
  return relative.format(Math.round(seconds / 86400), 'day')
}

// The daily job runs Mon-Fri after the close, so a gap of up to ~3.5 days (a weekend) is normal.
export const STALE_AFTER_HOURS = 84

export function isStale(iso: string, now: Date = new Date()): boolean {
  return now.getTime() - new Date(iso).getTime() > STALE_AFTER_HOURS * 3600 * 1000
}

/** A calendar date like "2026-10-09" -> "Oct 9, 2026" (no time-zone shift). */
export function formatDay(ymd: string): string {
  return day.format(new Date(`${ymd}T00:00:00Z`))
}

export function formatPrice(v: number): string {
  const digits = Math.abs(v) < 1 ? 4 : 2
  return `$${v.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

/** Signed percentage with a real minus sign, so the sign is readable without colour. */
export function formatPct(v: number, digits = 1): string {
  const s = (Math.abs(v) * 100).toFixed(digits)
  if (Number(s) === 0) return `${(0).toFixed(digits)}%`
  return `${v > 0 ? '+' : '−'}${s}%`
}

export function formatPctAbs(v: number, digits = 1): string {
  return `${(v * 100).toFixed(digits)}%`
}

export function formatMoney(v: number): string {
  return `$${compact.format(v)}`
}

export function formatNum(v: number, digits = 2): string {
  return Math.abs(v) >= 1000 ? int.format(v) : v.toFixed(digits)
}

export function formatInt(v: number): string {
  return int.format(v)
}

/** Tailwind classes for a signed value. Always paired with a +/− sign in the text. */
export function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0 || Number.isNaN(v)) return ''
  return v > 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'
}
