export type IconName = 'today' | 'screener' | 'portfolio' | 'health' | 'more'

export interface NavItem {
  to: string
  label: string
  icon?: IconName
}

/** Shown in the phone bottom bar (plus "More"). */
export const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Today', icon: 'today' },
  { to: '/screener', label: 'Screener', icon: 'screener' },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
  { to: '/health', label: 'Health', icon: 'health' },
]

/** Listed on the "More" page on phones; inline in the top bar on wider screens. */
export const SECONDARY_NAV: NavItem[] = [
  { to: '/compare', label: 'Compare' },
  { to: '/scorecard', label: 'Scorecard' },
  { to: '/baseline-race', label: 'Baseline race' },
  { to: '/validation', label: 'Validation' },
  { to: '/about', label: 'About & method' },
]
