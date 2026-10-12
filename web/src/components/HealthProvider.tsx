import type { ReactNode } from 'react'
import { useSiteJson } from '../lib/data'
import { HealthContext } from '../lib/health'
import type { Health } from '../types'

export function HealthProvider({ children }: { children: ReactNode }) {
  const health = useSiteJson<Health>('health.json')
  return <HealthContext value={health}>{children}</HealthContext>
}
