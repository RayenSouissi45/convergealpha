// The opportunity badge's texts and the lazily loaded opportunities.json (see components/Opportunity).

import { useEffect, useState } from 'react'
import type { Tone } from '../components/ui'
import type { Cell, OppColor, OpportunitiesFile } from '../types'
import { fetchSiteJson, type Loadable } from './data'

export const OPP_TEXT: Record<OppColor, { title: string; short: string; tone: Tone; help: string }> = {
  green: {
    title: 'Confirmed opportunity',
    short: 'Confirmed',
    tone: 'good',
    help: 'A fresh positive event whose kind passed the luck test, at least 3 evidence families at 60+, a validated chance up 3+ points above usual, not blocked.',
  },
  amber: {
    title: 'Possible, not confirmed',
    short: 'Possible',
    tone: 'warn',
    help: 'A fresh positive event, but the evidence or the validation is missing or weak.',
  },
  red: {
    title: 'Hype / be careful',
    short: 'Be careful',
    tone: 'bad',
    help: 'A big jump, a fresh event or loud news together with weak evidence or a risk (heavy short selling, share offering, going-concern warning…).',
  },
}

export function isOpp(v: Cell | undefined): v is OppColor {
  return v === 'green' || v === 'amber' || v === 'red'
}

let cache: Promise<Loadable<OpportunitiesFile>> | null = null

/** opportunities.json, loaded once (only when a "Why?" panel is opened). */
export function useOpportunities(enabled: boolean): Loadable<OpportunitiesFile> {
  const [state, setState] = useState<Loadable<OpportunitiesFile>>({ state: 'loading' })
  useEffect(() => {
    if (!enabled) return
    let alive = true
    if (!cache) cache = fetchSiteJson<OpportunitiesFile>('opportunities.json')
    void cache.then((v) => {
      if (alive) setState(v)
      if (v.state === 'error') cache = null
    })
    return () => {
      alive = false
    }
  }, [enabled])
  return state
}

/** For tests. */
export function resetOpportunities(): void {
  cache = null
}

