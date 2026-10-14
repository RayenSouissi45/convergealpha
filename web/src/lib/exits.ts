// "What if I had sold differently?": each of your closed trades replayed with the sell rule the app
// tested once on 2016-2023 (sell at the next open after a close 5% below the buy price or 6% above
// it, or after 63 trading days). Price change only (no fees, no euro moves), from the stock's daily
// prices on its page; the buy is taken at the opening price of your buy day.

import type { ChartArrays } from '../types'

export const RULE = { stop: 0.05, takeProfit: 0.06, maxDays: 63 } as const

export interface RuleResult {
  ret: number
  date: string
  why: 'stop' | 'take profit' | '63 days' | 'still holding'
}

export function ruleExit(daily: NonNullable<ChartArrays['daily']>, buyDate: string): RuleResult | null {
  const i0 = daily.t.findIndex((d) => d >= buyDate)
  if (i0 < 0) return null
  const entry = daily.o[i0] ?? daily.c[i0]
  if (!entry || !(entry > 0)) return null
  const last = Math.min(daily.t.length - 1, i0 + RULE.maxDays - 1)
  for (let k = i0; k <= last; k++) {
    const c = daily.c[k]
    if (c === null || c === undefined) continue
    const hit = c <= entry * (1 - RULE.stop) ? 'stop' : c >= entry * (1 + RULE.takeProfit) ? 'take profit' : null
    if (hit) {
      if (k + 1 >= daily.t.length) return { ret: c / entry - 1, date: daily.t[k] as string, why: 'still holding' }
      const out = daily.o[k + 1] ?? daily.c[k + 1] ?? c
      return { ret: out / entry - 1, date: daily.t[k + 1] as string, why: hit }
    }
  }
  const c = daily.c[last] ?? entry
  return { ret: c / entry - 1, date: daily.t[last] as string, why: last === i0 + RULE.maxDays - 1 ? '63 days' : 'still holding' }
}
