// Plan builder math: your sliders and period -> candidates, their euro outcomes after costs, and a
// verdict. Every rule and threshold is fixed (docs/METHODOLOGY.md, "Plan builder") and mirrored
// from pipeline/src/convergealpha/decide/plan.py (THRESHOLDS); a test pins both.

import type { HorizonKey } from './columns'
import { breakEven, buy, result, roundTripEuros, type Buy, type Fees } from './costs'
import type { PlanFile, ReliabilityBucket } from '../types'

export const H_DAYS: Record<HorizonKey, number> = { '1w': 5, '1m': 21, '3m': 63, '6m': 126 }
const PAIRS: [HorizonKey, HorizonKey][] = [
  ['1w', '1m'],
  ['1m', '3m'],
  ['3m', '6m'],
]

export const THRESHOLDS = {
  green_p_profit: 0.55,
  green_reliability_lo: 0.52,
  amber_p_profit: 0.5,
  confidence_weight: 5,
  trading_days_per_day: 0.7,
} as const

// Normal-curve distances of the 25th/75th and 10th/90th percentiles from the middle.
const Z25 = 0.6745
const Z10 = 1.2816

/** Slider 1..10 -> minimum sub-score: 1 -> 0, 10 -> 90 (straight line). */
export function sliderMin(s: number): number {
  return (Math.round(s) - 1) * 10
}

/** Calendar days -> trading days: 30 days = 21 trading days (×0.7). */
export function tradingDays(days: number): number {
  return Math.round(days * THRESHOLDS.trading_days_per_day)
}

export interface HorizonMix {
  td: number
  a: HorizonKey
  b: HorizonKey
  /** Weight of `b` (0 = only `a`). */
  w: number
  exact: boolean
  /** Shorter than the shortest forecast: the 1-week forecast is used. */
  short: boolean
  used: HorizonKey[]
  text: string
}

const NAME: Record<HorizonKey, string> = { '1w': '1-week', '1m': '1-month', '3m': '3-month', '6m': '6-month' }

/** Map a period to the forecast horizons: one horizon, or a straight-line mix of the nearest two. */
export function mapPeriod(days: number): HorizonMix {
  const td = tradingDays(days)
  if (td <= H_DAYS['1w']) {
    const short = td < H_DAYS['1w']
    return {
      td,
      a: '1w',
      b: '1w',
      w: 0,
      exact: !short,
      short,
      used: ['1w'],
      text: short
        ? `${td} trading days is shorter than the shortest forecast, so the 1-week forecast (5 trading days) is used.`
        : 'Uses the 1-week forecast (5 trading days).',
    }
  }
  for (const [a, b] of PAIRS) {
    if (td >= H_DAYS[a] && td <= H_DAYS[b]) {
      if (td === H_DAYS[a] || td === H_DAYS[b]) {
        const h = td === H_DAYS[a] ? a : b
        return { td, a: h, b: h, w: 0, exact: true, short: false, used: [h], text: `Uses the ${NAME[h]} forecast (${H_DAYS[h]} trading days).` }
      }
      const w = (td - H_DAYS[a]) / (H_DAYS[b] - H_DAYS[a])
      return {
        td,
        a,
        b,
        w,
        exact: false,
        short: false,
        used: [a, b],
        text: `${td} trading days is between the ${NAME[a]} and ${NAME[b]} forecasts, so every number is a straight-line mix of the two (${Math.round((1 - w) * 100)}% ${NAME[a]}, ${Math.round(w * 100)}% ${NAME[b]}).`,
      }
    }
  }
  return { td, a: '6m', b: '6m', w: 0, exact: td === 126, short: false, used: ['6m'], text: 'Uses the 6-month forecast (126 trading days).' }
}

/** The calibrated forecast at one horizon: chance up and the conformal-widened range. */
export interface Dist {
  pUp: number
  med: number
  p10: number
  p25: number
  p75: number
  p90: number
}

/** The 25th/75th percentiles sit between the middle and the widened 10th/90th on a bell shape. */
export function dist(pUp: number | null, med: number | null, p10: number | null, p90: number | null): Dist | null {
  if (pUp === null || med === null || p10 === null || p90 === null) return null
  return { pUp, med, p10, p25: med - (med - p10) * (Z25 / Z10), p75: med + (p90 - med) * (Z25 / Z10), p90 }
}

export function mix(a: Dist, b: Dist, w: number): Dist {
  const m = (x: number, y: number) => x + (y - x) * w
  return { pUp: m(a.pUp, b.pUp), med: m(a.med, b.med), p10: m(a.p10, b.p10), p25: m(a.p25, b.p25), p75: m(a.p75, b.p75), p90: m(a.p90, b.p90) }
}

/** The four straight segments of the distribution: [return, level] at each end. */
type Segment = { x0: number; l0: number; x1: number; l1: number }

function segments(d: Dist): Segment[] {
  return [
    { x0: d.p10, l0: 0.1, x1: d.p25, l1: 0.25 },
    { x0: d.p25, l0: 0.25, x1: d.med, l1: 0.5 },
    { x0: d.med, l0: 0.5, x1: d.p75, l1: 0.75 },
    { x0: d.p75, l0: 0.75, x1: d.p90, l1: 0.9 },
  ]
}

/** The segment a value falls in; below the first or above the last, the outer one (extended). */
function pick(segs: Segment[], v: number, key: 'x' | 'l'): Segment {
  const hi = (s: Segment) => (key === 'x' ? s.x1 : s.l1)
  return segs.slice(0, -1).find((s) => v <= hi(s)) ?? segs[segs.length - 1]!
}

/** Share of outcomes at or below `x`: straight lines through the five percentiles, extended past them. */
export function cdf(d: Dist, x: number): number {
  const s = pick(segments(d), x, 'x')
  const span = s.x1 - s.x0
  const f = span > 0 ? s.l0 + ((x - s.x0) / span) * (s.l1 - s.l0) : x < s.x0 ? s.l0 : s.l1
  return Math.min(1, Math.max(0, f))
}

/** The return at quantile level u (inverse of cdf, same straight lines, extended past the ends). */
export function quantile(d: Dist, u: number): number {
  const s = pick(segments(d), u, 'l')
  return s.x0 + ((u - s.l0) / (s.l1 - s.l0)) * (s.x1 - s.x0)
}

/** Chance the return ends above `x`, anchored on the calibrated chance up: the range only moves
 * it from 0 to `x` (the cost hurdle). */
export function chanceAbove(d: Dist, x: number): number {
  return Math.min(1, Math.max(0, d.pUp - (cdf(d, x) - cdf(d, 0))))
}

export interface Rel {
  rate: number
  lo: number
  hi: number
  n: number
}

export function findRel(buckets: ReliabilityBucket[] | undefined, p: number | null): Rel | null {
  if (!buckets || p === null) return null
  const b = buckets.find((x) => x.lo <= p && p < x.hi)
  return b ? { rate: b.rate, lo: b.wilson_lo, hi: b.wilson_hi, n: b.n } : null
}

export function mixRel(a: Rel | null, b: Rel | null, w: number): Rel | null {
  if (w === 0) return a
  if (w === 1) return b
  if (!a || !b) return null
  const m = (x: number, y: number) => x + (y - x) * w
  return { rate: m(a.rate, b.rate), lo: m(a.lo, b.lo), hi: m(a.hi, b.hi), n: Math.min(a.n, b.n) }
}

export type VerdictColor = 'green' | 'amber' | 'grey'

export interface Verdict {
  color: VerdictColor
  title: string
  why: string[]
}

export function verdict(v: { pProfit: number; relLo: number | null; middle: number; validated: boolean }): Verdict {
  const checks: [boolean, string][] = [
    [v.pProfit >= THRESHOLDS.green_p_profit, `chance of ending with more money after costs ${Math.round(v.pProfit * 100)}% (needs ${Math.round(THRESHOLDS.green_p_profit * 100)}%)`],
    [v.relLo !== null && v.relLo >= THRESHOLDS.green_reliability_lo, v.relLo === null ? 'no past record for this chance' : `low end of “how often right” ${Math.round(v.relLo * 100)}% (needs ${Math.round(THRESHOLDS.green_reliability_lo * 100)}%)`],
    [v.middle > 0, v.middle > 0 ? 'the middle outcome is larger than the costs' : 'the middle outcome does not cover the costs'],
    [v.validated, v.validated ? 'the forecast for this period is validated' : 'the forecast for this period is not validated (research mode)'],
  ]
  if (checks.every(([ok]) => ok)) return { color: 'green', title: 'Good opportunity now', why: checks.map(([, t]) => t) }
  const why = checks.filter(([ok]) => !ok).map(([, t]) => t)
  if (v.pProfit >= THRESHOLDS.amber_p_profit && v.middle > 0) return { color: 'amber', title: 'Possible but weak', why }
  return { color: 'grey', title: 'No good opportunity now: waiting is a valid choice', why }
}

// ---------------------------------------------------------------- the stocks

export interface PlanRow {
  ticker: string
  name: string | null
  sector: string | null
  zero: boolean | null
  label: string
  price: number | null
  spread: number
  safety: number | null
  upside: number | null
  confidence: number | null
  balanced: number | null
  days_to_earnings: number | null
  next_earnings: string | null
  opp: string | null
  opp_event: string | null
  [key: string]: string | number | boolean | null
}

export function toPlanRows(f: PlanFile): PlanRow[] {
  return f.rows.map((r) => Object.fromEntries(f.fields.map((k, i) => [k, r[i] ?? null])) as PlanRow)
}

export function horizonDist(r: PlanRow, h: HorizonKey): Dist | null {
  const n = (k: string) => (typeof r[k] === 'number' ? (r[k] as number) : null)
  return dist(n(`p_up_${h}`), n(`med_${h}`), n(`p10_${h}`), n(`p90_${h}`))
}

export function periodDist(r: PlanRow, m: HorizonMix): Dist | null {
  const a = horizonDist(r, m.a)
  if (m.w === 0) return a
  const b = horizonDist(r, m.b)
  return a && b ? mix(a, b, m.w) : null
}

export interface RankOptions {
  safety: number
  upside: number
  td: number
  allowEarnings: boolean
  onlyZero: boolean
}

export interface Ranked {
  rows: PlanRow[]
  left: { safety: number; upside: number; earnings: number; noDate: number; zero: number }
}

/** Mix = (S × Safety + U × Upside + 5 × Confidence) ÷ (S + U + 5), after the minimum scores. */
export function rank(all: PlanRow[], o: RankOptions): Ranked {
  const left = { safety: 0, upside: 0, earnings: 0, noDate: 0, zero: 0 }
  const minS = sliderMin(o.safety)
  const minU = sliderMin(o.upside)
  const keep = all.filter((r) => {
    if (o.onlyZero && r.zero === false) return (left.zero++, false)
    if ((r.safety ?? -1) < minS) return (left.safety++, false)
    if ((r.upside ?? -1) < minU) return (left.upside++, false)
    if (!o.allowEarnings) {
      if (r.days_to_earnings === null) return (left.noDate++, false)
      if (r.days_to_earnings >= 0 && r.days_to_earnings <= o.td) return (left.earnings++, false)
    }
    return true
  })
  const c = THRESHOLDS.confidence_weight
  const score = (r: PlanRow) => (o.safety * (r.safety ?? 0) + o.upside * (r.upside ?? 0) + c * (r.confidence ?? 0)) / (o.safety + o.upside + c)
  keep.sort((a, b) => score(b) - score(a) || (b.confidence ?? 0) - (a.confidence ?? 0) || a.ticker.localeCompare(b.ticker))
  return { rows: keep, left }
}

export interface Evaluation {
  buy: Buy
  spread: number
  breakEven: number
  pProfit: number
  middle: number
  bad: number
  good: number
  /** Buy fee + sell fee. */
  fees: number
  /** Fees and the spread both ways, in euros. */
  costs: number
  rel: Rel | null
  validated: boolean
  verdict: Verdict
}

export interface Context {
  fx: number
  fees: Fees
  mix: HorizonMix
  reliability: Record<string, ReliabilityBucket[]>
  validated: string[]
}

function relFor(r: PlanRow, c: Context): Rel | null {
  const p = (h: HorizonKey) => (typeof r[`p_up_${h}`] === 'number' ? (r[`p_up_${h}`] as number) : null)
  const a = findRel(c.reliability[c.mix.a], p(c.mix.a))
  if (c.mix.w === 0) return a
  return mixRel(a, findRel(c.reliability[c.mix.b], p(c.mix.b)), c.mix.w)
}

function isValidated(c: Context): boolean {
  return c.mix.used.every((h) => c.validated.includes(`P(up) ${h}`))
}

/** One stock bought with `amount` euros and held for the period. Null if not affordable. */
export function evaluate(r: PlanRow, amount: number, c: Context): Evaluation | null {
  const d = periodDist(r, c.mix)
  if (!d || r.price === null) return null
  const b = buy(amount, r.price, c.fx, r.spread, c.fees)
  if (b.shares <= 0) return null
  const be = breakEven(b, r.spread, c.fees.sell)
  const pProfit = chanceAbove(d, be)
  const middle = result(b, d.med, r.spread, c.fees.sell)
  const rel = relFor(r, c)
  const validated = isValidated(c)
  return {
    buy: b,
    spread: r.spread,
    breakEven: be,
    pProfit,
    middle,
    bad: result(b, d.p10, r.spread, c.fees.sell),
    good: result(b, d.p90, r.spread, c.fees.sell),
    fees: b.fee + c.fees.sell,
    costs: roundTripEuros(b, r.spread, c.fees.sell),
    rel,
    validated,
    verdict: verdict({ pProfit, relLo: rel?.lo ?? null, middle, validated }),
  }
}

export interface SplitEvaluation {
  legs: [Evaluation, Evaluation]
  shares: number
  leftover: number
  fees: number
  spent: number
  breakEven: number
  pProfit: number
  middle: number
  bad: number
  good: number
  rel: Rel | null
  validated: boolean
  verdict: Verdict
}

/** Half the amount in each of two stocks. Cautious assumption: they move together (outcomes at
 * the same percentile add up), so the range is as wide as it can be. */
export function evaluateSplit(r1: PlanRow, r2: PlanRow, amount: number, c: Context): SplitEvaluation | null {
  const e1 = evaluate(r1, amount / 2, c)
  const e2 = evaluate(r2, amount / 2, c)
  const d1 = periodDist(r1, c.mix)
  const d2 = periodDist(r2, c.mix)
  if (!e1 || !e2 || !d1 || !d2) return null
  // Anchored quantiles: the same shift as chanceAbove, so a single stock gives the same answer.
  const anchored = (d: Dist) => {
    const shift = 1 - d.pUp - cdf(d, 0)
    return (u: number) => quantile(d, u - shift)
  }
  const q1 = anchored(d1)
  const q2 = anchored(d2)
  const total = (u: number) => result(e1.buy, q1(u), r1.spread, c.fees.sell) + result(e2.buy, q2(u), r2.spread, c.fees.sell)
  let lo = -0.5
  let hi = 1.5
  for (let i = 0; i < 60; i++) {
    const m = (lo + hi) / 2
    if (total(m) > 0) hi = m
    else lo = m
  }
  const pProfit = Math.min(1, Math.max(0, 1 - (lo + hi) / 2))
  const middle = e1.middle + e2.middle
  const spent = e1.buy.spent + e2.buy.spent
  const rel = e1.rel && e2.rel ? (e1.rel.lo <= e2.rel.lo ? e1.rel : e2.rel) : null
  const validated = e1.validated && e2.validated
  const value = e1.buy.shares * e1.buy.midEur + e2.buy.shares * e2.buy.midEur
  return {
    legs: [e1, e2],
    shares: e1.buy.shares + e2.buy.shares,
    leftover: e1.buy.leftover + e2.buy.leftover,
    fees: e1.buy.fee + e2.buy.fee + 2 * c.fees.sell,
    spent,
    // Break-even for the pair, as a share of the stock value bought (both legs move alike).
    breakEven: value > 0 ? (spent + 2 * c.fees.sell) / (e1.buy.shares * e1.buy.midEur * (1 - r1.spread / 2) + e2.buy.shares * e2.buy.midEur * (1 - r2.spread / 2)) - 1 : NaN,
    pProfit,
    middle,
    bad: e1.bad + e2.bad,
    good: e1.good + e2.good,
    rel,
    validated,
    verdict: verdict({ pProfit, relLo: rel?.lo ?? null, middle, validated }),
  }
}
