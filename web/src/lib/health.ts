import { createContext, useContext } from 'react'
import type { Health } from '../types'
import type { Loadable } from './data'

export const HealthContext = createContext<Loadable<Health>>({ state: 'loading' })

/** health.json, loaded once by <HealthProvider> for the whole app. */
export function useHealth(): Loadable<Health> {
  return useContext(HealthContext)
}
