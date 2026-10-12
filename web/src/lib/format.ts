// The interface is English, so formats are English too (in the viewer's own time zone).
const LOCALE = 'en-US'
const dateTime = new Intl.DateTimeFormat(LOCALE, { dateStyle: 'medium', timeStyle: 'short' })
const newYork = new Intl.DateTimeFormat(LOCALE, {
  timeZone: 'America/New_York',
  dateStyle: 'medium',
  timeStyle: 'short',
})
const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto', style: 'short' })

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
