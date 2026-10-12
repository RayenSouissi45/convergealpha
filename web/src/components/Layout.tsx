import { Link, NavLink, Outlet } from 'react-router'
import { formatAge, isStale } from '../lib/format'
import { useHealth } from '../lib/health'
import { useTheme, type ThemePref } from '../lib/theme'
import { PRIMARY_NAV, SECONDARY_NAV } from '../nav'
import { Icon } from './Icon'

const THEME_LABEL: Record<ThemePref, string> = { system: 'Auto', light: 'Light', dark: 'Dark' }
const THEME_ICON = { system: 'auto', light: 'sun', dark: 'moon' } as const

function ThemeToggle() {
  const { pref, cycle } = useTheme()
  return (
    <button
      type="button"
      onClick={cycle}
      className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-sm text-slate-600 hover:bg-slate-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
      aria-label={`Theme: ${THEME_LABEL[pref]}. Tap to change.`}
    >
      <Icon name={THEME_ICON[pref]} className="size-4" />
      <span className="hidden sm:inline">{THEME_LABEL[pref]}</span>
    </button>
  )
}

function DataStatus() {
  const health = useHealth()
  let text = 'Loading…'
  let dot = 'bg-slate-400'
  if (health.state === 'missing') {
    text = 'No data yet'
  } else if (health.state === 'error') {
    text = 'Data error'
    dot = 'bg-red-500'
  } else if (health.state === 'ready') {
    const stale = isStale(health.data.generated_at)
    text = `${stale ? 'Stale · ' : 'Updated '}${formatAge(health.data.generated_at)}`
    dot = stale || health.data.status !== 'ok' ? 'bg-amber-500' : 'bg-emerald-500'
  }
  return (
    <Link
      to="/health"
      className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs whitespace-nowrap text-slate-600 hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
    >
      <span className={`size-2 rounded-full ${dot}`} aria-hidden="true" />
      {text}
    </Link>
  )
}

const desktopLink = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-2.5 py-1.5 text-sm whitespace-nowrap ${
    isActive
      ? 'bg-slate-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
      : 'text-slate-600 hover:bg-slate-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
  }`

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-slate-50/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
      <div className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-1">
        <Link to="/" className="mr-auto flex min-h-11 items-center gap-2 font-semibold tracking-tight">
          <img src="./favicon.svg" alt="" className="size-7" />
          <span>ConvergeAlpha</span>
        </Link>
        <DataStatus />
        <ThemeToggle />
      </div>
      <nav aria-label="Main" className="mx-auto hidden max-w-5xl gap-0.5 px-3 pb-2 lg:flex">
        {[...PRIMARY_NAV, ...SECONDARY_NAV].map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={desktopLink}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}

function Banners() {
  const health = useHealth()
  const data = health.state === 'ready' ? health.data : null
  return (
    <div className="mx-auto w-full max-w-5xl space-y-2 px-4 pt-3">
      {data?.kill_switch.active && (
        <div role="alert" className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          <strong>KILL SWITCH ACTIVE — no new BUY labels.</strong> {data.kill_switch.reasons.join(' · ')}
        </div>
      )}
      {data && isStale(data.generated_at) && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Data may be out of date.</strong> The last update was {formatAge(data.generated_at)}.{' '}
          <Link to="/health" className="underline">
            Check Health
          </Link>
        </div>
      )}
      {(data === null || data.research_mode) && (
        <aside
          aria-label="Research mode"
          className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100"
        >
          <strong className="font-semibold tracking-wide">RESEARCH MODE — not yet validated.</strong>{' '}
          <span className="hidden sm:inline">
            No percentage on this site has passed the validation lab yet.{' '}
          </span>
          Not financial advice.{' '}
          <Link to="/about" className="underline underline-offset-2">
            What this means
          </Link>
        </aside>
      )}
    </div>
  )
}

const bottomLink = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
    isActive ? 'text-teal-700 dark:text-teal-400' : 'text-slate-500 dark:text-zinc-400'
  }`

function BottomNav() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden dark:border-zinc-800 dark:bg-zinc-950/95"
    >
      <div className="mx-auto flex max-w-md">
        {[...PRIMARY_NAV, { to: '/more', label: 'More', icon: 'more' as const }].map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={bottomLink}>
            {item.icon && <Icon name={item.icon} className="size-6" />}
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

function Footer() {
  const health = useHealth()
  return (
    <footer className="mx-auto w-full max-w-5xl px-4 pt-6 pb-28 text-xs text-slate-500 lg:pb-8 dark:text-zinc-500">
      <p>
        Not financial advice. No tool can make a stock rise for sure. No ads, no tracking — your
        portfolio stays in this browser.
      </p>
      {health.state === 'ready' && (
        <p className="mt-1">
          Build phase {health.data.build_phase} · pipeline v{health.data.pipeline_version}
        </p>
      )}
    </footer>
  )
}

export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <Header />
      <Banners />
      {/* Full-height main keeps the footer below the fold while data loads (no layout shift). */}
      <main id="main" className="mx-auto min-h-dvh w-full max-w-5xl flex-1 px-4 pt-4">
        <Outlet />
      </main>
      <Footer />
      <BottomNav />
    </div>
  )
}
