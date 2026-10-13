// "Only stocks I can buy on finanzen.net zero": one setting shared by every page, remembered in
// this browser. A stock is true (on the broker's list), false (not on it) or null (unknown). Unknown
// is never treated as "not buyable": with the box ticked, unknown stocks stay visible, marked "?".

import { useSyncExternalStore } from 'react'
import type { BrokerSummary, Cell } from '../types'
import { formatDay } from './format'
import { useHealth } from './health'

const KEY = 'ca-only-zero'
const listeners = new Set<() => void>()

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

let current: boolean | null = null

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function snapshot(): boolean {
  if (current === null) current = read()
  return current
}

export function setOnlyZero(on: boolean): void {
  current = on
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    // Storage blocked (private mode): the choice lasts for this visit only.
  }
  listeners.forEach((fn) => fn())
}

/** For tests: forget the in-memory value so the next read comes from storage. */
export function resetOnlyZero(): void {
  current = null
}

/** [ticked, setTicked], shared by Screener, Picks, Today and Compare. */
export function useOnlyZero(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, snapshot, () => false)
  return [on, setOnlyZero]
}

/** The broker list summary from health.json (null until the weekly job has built it). */
export function useBrokerList(): BrokerSummary | null {
  const health = useHealth()
  return health.state === 'ready' ? (health.data.brokers ?? null) : null
}

export function zeroAvailability(b: BrokerSummary | null | undefined): { ok: boolean; why: string } {
  if (!b) {
    return {
      ok: false,
      why: 'The finanzen.net zero list is not available yet. It is built every Saturday from gettex’s official list (ESMA FIRDS).',
    }
  }
  if (b.stale) {
    return {
      ok: false,
      why: `The finanzen.net zero list is ${b.age_days ?? 'many'} days old, too old to trust. Every stock shows as "not sure" until the weekly refresh works again.`,
    }
  }
  return { ok: true, why: '' }
}

/** Keep a row? Unknown (null) is kept: it is never treated as "not buyable". */
export function zeroKeep(v: Cell | undefined, on: boolean): boolean {
  return !on || v !== false
}

export function zeroCounts(values: (Cell | undefined)[]): { yes: number; no: number; unknown: number } {
  let yes = 0
  let no = 0
  let unknown = 0
  for (const v of values) {
    if (v === true) yes++
    else if (v === false) no++
    else unknown++
  }
  return { yes, no, unknown }
}

export function listDateText(b: BrokerSummary | null | undefined): string {
  return b?.list_date ? formatDay(b.list_date) : 'unknown date'
}
