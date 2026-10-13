import { useSyncExternalStore } from 'react'

/** True while the media query matches (e.g. a phone-width screen). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const m = window.matchMedia?.(query)
      m?.addEventListener('change', onChange)
      return () => m?.removeEventListener('change', onChange)
    },
    () => window.matchMedia?.(query).matches ?? false,
    () => false,
  )
}

/** Phones: the screener shows one forecast horizon at a time so it never scrolls sideways. */
export const PHONE = '(max-width: 639px)'
