import { useCallback, useEffect, useState } from 'react'

export type ThemePref = 'system' | 'light' | 'dark'

const KEY = 'ca-theme'
const ORDER: ThemePref[] = ['system', 'light', 'dark']

function readPref(): ThemePref {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

function apply(pref: ThemePref): void {
  const dark =
    pref === 'dark' ||
    (pref === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', Boolean(dark))
}

export function useTheme(): { pref: ThemePref; cycle: () => void } {
  const [pref, setPref] = useState<ThemePref>(readPref)

  useEffect(() => {
    apply(pref)
    if (pref !== 'system' || !window.matchMedia) return
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => apply('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [pref])

  const cycle = useCallback(() => {
    setPref((current) => {
      const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length] ?? 'system'
      try {
        localStorage.setItem(KEY, next)
      } catch {
        // Storage can be blocked (private mode); the choice then lasts for this visit only.
      }
      return next
    })
  }, [])

  return { pref, cycle }
}
