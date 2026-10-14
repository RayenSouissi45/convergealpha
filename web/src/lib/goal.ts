// Savings plan and goal planner: thousands of possible futures replayed from about 100 years of
// real US market history (Kenneth R. French Data Library), in 12-month blocks so that crashes,
// recoveries and long bad stretches keep their real shape. Nothing here is a forecast: it shows
// how the same plan would have turned out across history, with fees, inflation and German tax.

import { taxOnGain, type TaxProfile } from './taxes'

export interface History {
  source?: string
  months: string[]
  market: (number | null)[]
  rf: (number | null)[]
  inflation: (number | null)[]
}

export interface GoalInput {
  /** Euros you invest now (after keeping your emergency cash aside). */
  start: number
  /** Euros added every month (at the start of the month). */
  monthly: number
  years: number
  /** The amount you want to reach, in today's euros when `real` is on. 0 = no goal. */
  goal: number
  /** Share in stocks (a broad stock ETF), 0..1; the rest earns the Treasury-bill rate. */
  stocks: number
  /** Yearly fund cost (TER), e.g. 0.002 = 0.2%. */
  ter: number
  /** Show everything in today's euros (after inflation). */
  real: boolean
  /** Assume stocks earn 2 percentage points a year less than they did in history. */
  cautious: boolean
}

export const CAUTIOUS_HAIRCUT = 0.02
export const PATHS = 4000
export const BLOCK = 12

/** Small, fast, seeded random numbers: the same plan always shows the same picture. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

interface Month {
  market: number
  rf: number
  inflation: number
}

/** The months usable for this plan: all with returns (and inflation when shown in today's euros). */
export function usableMonths(h: History, real: boolean): Month[] {
  const out: Month[] = []
  for (let i = 0; i < h.months.length; i++) {
    const m = h.market.at(i)
    const r = h.rf.at(i)
    const inf = h.inflation.at(i)
    if (m === null || m === undefined || r === null || r === undefined) continue
    if (real && (inf === null || inf === undefined)) continue
    out.push({ market: m, rf: r, inflation: inf ?? 0 })
  }
  return out
}

/** Per path and year y: A = growth of 1 € put in at the start, B = value of 1 € added every month,
 * I = cumulative inflation. A plan's value is start × A + monthly × B (÷ I in today's euros), so
 * chances and the monthly amount needed come out exactly, without re-simulating. */
export interface Paths {
  years: number
  n: number
  /** n × (years + 1), row-major. */
  A: Float64Array
  B: Float64Array
  I: Float64Array
  /** Months the history covers, e.g. "1926-07 to 2026-08". */
  span: string
}

export function simulate(h: History, input: Pick<GoalInput, 'years' | 'stocks' | 'ter' | 'real' | 'cautious'>, n = PATHS, seed = 7): Paths {
  const ms = usableMonths(h, input.real)
  const years = Math.max(1, Math.round(input.years))
  const cols = years + 1
  const A = new Float64Array(n * cols)
  const B = new Float64Array(n * cols)
  const I = new Float64Array(n * cols)
  const firstUsable = h.months.find((_, i) => h.market.at(i) !== null && h.rf.at(i) !== null) ?? ''
  const span = ms.length ? `${firstUsable} to ${h.months.at(-1) ?? ''}` : ''
  if (ms.length < BLOCK * 2) return { years, n: 0, A, B, I, span }
  const rand = mulberry32(seed)
  const haircut = input.cautious ? CAUTIOUS_HAIRCUT / 12 : 0
  const s = Math.min(1, Math.max(0, input.stocks))
  const fee = input.ter / 12
  for (let p = 0; p < n; p++) {
    let a = 1
    let b = 0
    let inf = 1
    A[p * cols] = 1
    B[p * cols] = 0
    I[p * cols] = 1
    let k = 0
    let block = 0
    for (let y = 1; y <= years; y++) {
      for (let m = 0; m < 12; m++) {
        if (k === 0) block = Math.floor(rand() * (ms.length - BLOCK + 1))
        const mo = ms[block + k] as Month
        k = (k + 1) % BLOCK
        const r = s * (mo.market - haircut) + (1 - s) * mo.rf - fee
        b = (b + 1) * (1 + r)
        a = a * (1 + r)
        inf = inf * (1 + mo.inflation)
      }
      A[p * cols + y] = a
      B[p * cols + y] = b
      I[p * cols + y] = input.real ? inf : 1
    }
  }
  return { years, n, A, B, I, span }
}

const sorted = (xs: Float64Array) => Float64Array.from(xs).sort()

/** The q-quantile (0..1) of sorted values. */
export function q(sortedXs: Float64Array, p: number): number {
  if (sortedXs.length === 0) return NaN
  const i = Math.min(sortedXs.length - 1, Math.max(0, Math.round(p * (sortedXs.length - 1))))
  return sortedXs[i] as number
}

/** Values of the plan in year y on every path (today's euros if the paths are real). */
export function valuesAt(ps: Paths, start: number, monthly: number, y: number): Float64Array {
  const cols = ps.years + 1
  const out = new Float64Array(ps.n)
  for (let p = 0; p < ps.n; p++) {
    const j = p * cols + y
    out[p] = (start * (ps.A[j] as number) + monthly * (ps.B[j] as number)) / (ps.I[j] as number)
  }
  return out
}

export interface Fan {
  year: number
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
  /** Money paid in so far (nominal euros). */
  paidIn: number
}

export function fan(ps: Paths, start: number, monthly: number): Fan[] {
  const out: Fan[] = []
  for (let y = 0; y <= ps.years; y++) {
    const v = sorted(valuesAt(ps, start, monthly, y))
    out.push({ year: y, p10: q(v, 0.1), p25: q(v, 0.25), p50: q(v, 0.5), p75: q(v, 0.75), p90: q(v, 0.9), paidIn: start + monthly * 12 * y })
  }
  return out
}

/** Share of futures that reach the goal at the end. */
export function chance(ps: Paths, start: number, monthly: number, goal: number): number {
  if (!(goal > 0) || ps.n === 0) return NaN
  const v = valuesAt(ps, start, monthly, ps.years)
  let hit = 0
  for (const x of v) if (x >= goal) hit++
  return hit / ps.n
}

/** The monthly amount that reaches the goal in `p` of the futures (exact: values are linear in it). */
export function monthlyNeeded(ps: Paths, start: number, goal: number, p: number): number {
  if (!(goal > 0) || ps.n === 0) return NaN
  const cols = ps.years + 1
  const need = new Float64Array(ps.n)
  for (let i = 0; i < ps.n; i++) {
    const j = i * cols + ps.years
    const target = goal * (ps.I[j] as number) - start * (ps.A[j] as number)
    need[i] = Math.max(0, target / (ps.B[j] as number))
  }
  return q(sorted(need), p)
}

/** After German tax on selling everything at the end (equity ETF: 30% of the gain is tax free;
 * the yearly advance tax is counted at the end, which it is credited against). Nominal euros. */
export function afterTax(value: number, paidIn: number, profile: TaxProfile | null): number {
  if (!profile) return value
  return paidIn + taxOnGain(value - paidIn, profile, 'equityFund').net
}

/** Monthly withdrawal that lasts `years` years in `p` of the futures, starting from `pot`
 * (sequence of returns included: a bad start hurts more). */
export function sustainableWithdrawal(h: History, pot: number, years: number, input: Pick<GoalInput, 'stocks' | 'ter' | 'real' | 'cautious'>, p = 0.9, n = 2000, seed = 11): number {
  if (!(pot > 0) || !(years > 0)) return 0
  const ms = usableMonths(h, input.real)
  if (ms.length < BLOCK * 2) return NaN
  const rand = mulberry32(seed)
  const haircut = input.cautious ? CAUTIOUS_HAIRCUT / 12 : 0
  const s = Math.min(1, Math.max(0, input.stocks))
  const fee = input.ter / 12
  const best = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    // Before month m the pot holds pot × a − w × b; taking w out must leave at least 0:
    // w ≤ pot × a / (b + 1). Then what is left grows: b = (b + 1) × g, a = a × g.
    let a = 1
    let b = 0
    let wMax = Infinity
    let k = 0
    let block = 0
    for (let m = 0; m < Math.round(years * 12); m++) {
      wMax = Math.min(wMax, (pot * a) / (b + 1))
      if (k === 0) block = Math.floor(rand() * (ms.length - BLOCK + 1))
      const mo = ms[block + k] as Month
      k = (k + 1) % BLOCK
      const r = s * (mo.market - haircut) + (1 - s) * mo.rf - fee
      const g = input.real ? (1 + r) / (1 + mo.inflation) : 1 + r
      b = (b + 1) * g
      a = a * g
    }
    best[i] = wMax
  }
  return q(sorted(best), 1 - p)
}
