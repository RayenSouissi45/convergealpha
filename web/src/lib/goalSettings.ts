// Your savings plan and goal, remembered in this browser only (like the trade settings).

import { useSyncExternalStore } from 'react'

export interface GoalSettings {
  have: number
  emergency: number
  monthly: number
  years: number
  goal: number
  /** Percent in stocks, 0..100. */
  stocksPct: number
  /** Yearly fund cost in percent, e.g. 0.2. */
  terPct: number
  real: boolean
  cautious: boolean
  /** Years of monthly withdrawals after the plan ends. */
  payoutYears: number
  /** When you saved the plan (ISO date), for the yearly review reminder. */
  savedOn: string | null
  /** The chance of reaching the goal when you saved it. */
  savedChance: number | null
}

export const DEFAULT_GOAL: GoalSettings = {
  have: 1000,
  emergency: 0,
  monthly: 100,
  years: 10,
  goal: 20000,
  stocksPct: 80,
  terPct: 0.2,
  real: true,
  cautious: false,
  payoutYears: 20,
  savedOn: null,
  savedChance: null,
}

const KEY = 'ca-goal-settings'
const listeners = new Set<() => void>()
let current: GoalSettings | null = null

function num(v: unknown, lo: number, hi: number, fallback: number): number {
  const n = typeof v === 'number' && Number.isFinite(v) ? v : fallback
  return Math.min(hi, Math.max(lo, n))
}

export function sanitizeGoal(raw: Partial<GoalSettings> | null | undefined): GoalSettings {
  const d = DEFAULT_GOAL
  const r = raw ?? {}
  return {
    have: num(r.have, 0, 100_000_000, d.have),
    emergency: num(r.emergency, 0, 100_000_000, d.emergency),
    monthly: num(r.monthly, 0, 1_000_000, d.monthly),
    years: Math.round(num(r.years, 1, 50, d.years)),
    goal: num(r.goal, 0, 1_000_000_000, d.goal),
    stocksPct: Math.round(num(r.stocksPct, 0, 100, d.stocksPct)),
    terPct: num(r.terPct, 0, 3, d.terPct),
    real: typeof r.real === 'boolean' ? r.real : d.real,
    cautious: typeof r.cautious === 'boolean' ? r.cautious : d.cautious,
    payoutYears: Math.round(num(r.payoutYears, 1, 50, d.payoutYears)),
    savedOn: typeof r.savedOn === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(r.savedOn) ? r.savedOn : null,
    savedChance: typeof r.savedChance === 'number' && r.savedChance >= 0 && r.savedChance <= 1 ? r.savedChance : null,
  }
}

function read(): GoalSettings {
  try {
    const v = localStorage.getItem(KEY)
    return sanitizeGoal(v ? (JSON.parse(v) as Partial<GoalSettings>) : null)
  } catch {
    return { ...DEFAULT_GOAL }
  }
}

function snapshot(): GoalSettings {
  if (current === null) current = read()
  return current
}

export function setGoal(patch: Partial<GoalSettings>): void {
  current = sanitizeGoal({ ...snapshot(), ...patch })
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    // Storage blocked: the plan lasts for this visit only.
  }
  listeners.forEach((fn) => fn())
}

/** For tests. */
export function resetGoal(): void {
  current = null
}

export function useGoalSettings(): [GoalSettings, (patch: Partial<GoalSettings>) => void] {
  const s = useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    snapshot,
    () => DEFAULT_GOAL,
  )
  return [s, setGoal]
}

/** A saved plan is due for a look once a year. */
export function reviewDue(s: GoalSettings, today = new Date()): boolean {
  if (!s.savedOn) return false
  return today.getTime() - new Date(`${s.savedOn}T00:00:00Z`).getTime() > 365 * 86400 * 1000
}
