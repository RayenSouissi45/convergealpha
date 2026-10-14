import type { StrategiesFile } from '../types'
import { useSiteJson } from './data'
import { useHealth } from './health'

export interface Fx {
  /** US dollars per euro. */
  rate: number
  date: string
  source: 'ECB' | 'FRED'
}

/** The latest EUR/USD rate: the European Central Bank's daily rate from the health file, else the
 * US central bank's (FRED) rate the strategies file carries. */
export function useFx(): Fx | null {
  const health = useHealth()
  const strategies = useSiteJson<StrategiesFile>('strategies.json')
  const latest = health.state === 'ready' ? health.data.fx_check?.latest : undefined
  if (latest?.ECB_USD) return { rate: latest.ECB_USD.rate, date: latest.ECB_USD.date, source: 'ECB' }
  if (latest?.DEXUSEU) return { rate: latest.DEXUSEU.rate, date: latest.DEXUSEU.date, source: 'FRED' }
  if (strategies.state === 'ready' && strategies.data.fx) return { rate: strategies.data.fx.rate, date: strategies.data.fx.date, source: 'FRED' }
  return null
}
