export type IconName = 'today' | 'picks' | 'plan' | 'screener' | 'portfolio' | 'health' | 'more'

export interface NavItem {
  to: string
  label: string
  icon?: IconName
}

/** Shown in the phone bottom bar (plus "More"). */
export const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Today', icon: 'today' },
  { to: '/picks', label: 'Picks', icon: 'picks' },
  { to: '/plan', label: 'Plan', icon: 'plan' },
  { to: '/screener', label: 'Screener', icon: 'screener' },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
]

/** Listed on the "More" page on phones; inline in the top bar on wider screens. */
export const SECONDARY_NAV: NavItem[] = [
  { to: '/strategies', label: 'Strategies' },
  { to: '/health', label: 'Health' },
  { to: '/compare', label: 'Compare' },
  { to: '/scorecard', label: 'Scorecard' },
  { to: '/baseline-race', label: 'Baseline race' },
  { to: '/validation', label: 'Validation' },
  { to: '/columns', label: 'Columns explained' },
  { to: '/about', label: 'About & method' },
]
