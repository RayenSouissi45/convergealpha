// Position sizing (spec section 7). Mirrors pipeline/src/convergealpha/core/stats.py exactly;
// both are tested against the same reference numbers.

export function kelly(p: number, b: number): number {
  if (b <= 0) throw new Error('payoff ratio must be positive')
  return p - (1 - p) / b
}

export function plannedExit(entry: number, atr: number): number {
  return Math.max(entry - 2 * atr, 0.92 * entry)
}

export interface SizingInput {
  equity: number
  entry: number
  exit: number
  gap: number
  pLower: number
  payoffB: number
  tierMultiplier?: number
  riskPerTrade?: number
  kellyMultiplier?: number
  maxPositionFrac?: number
  advShares?: number | null
  maxAdvFrac?: number
  /** Drawdown throttle: 1 normally, 0.5 after -10%, 0 after -15%. */
  throttle?: number
}

export interface SizingResult {
  shares: number
  riskPerShare: number
  binding: 'risk' | 'kelly' | 'max position' | 'liquidity' | 'throttle' | 'negative edge'
  caps: { risk: number; kelly: number; position: number; liquidity: number | null }
}

export function positionShares(i: SizingInput): SizingResult {
  const r = Math.max(i.entry - i.exit, i.gap)
  const tier = i.tierMultiplier ?? 1
  const throttle = i.throttle ?? 1
  const k = (i.kellyMultiplier ?? 0.25) * kelly(i.pLower, i.payoffB)
  const caps = {
    risk: ((i.riskPerTrade ?? 0.0075) * i.equity * tier * throttle) / r,
    kelly: k > 0 ? (k * i.equity) / i.entry : 0,
    position: ((i.maxPositionFrac ?? 0.1) * i.equity) / i.entry,
    liquidity: i.advShares ? (i.maxAdvFrac ?? 0.01) * i.advShares : null,
  }
  if (r <= 0 || i.entry <= 0 || i.equity <= 0) return { shares: 0, riskPerShare: r, binding: 'risk', caps }
  if (k <= 0) return { shares: 0, riskPerShare: r, binding: 'negative edge', caps }
  if (throttle === 0) return { shares: 0, riskPerShare: r, binding: 'throttle', caps }
  const entries: [SizingResult['binding'], number][] = [
    ['risk', caps.risk],
    ['kelly', caps.kelly],
    ['max position', caps.position],
  ]
  if (caps.liquidity !== null) entries.push(['liquidity', caps.liquidity])
  entries.sort((a, b) => a[1] - b[1])
  const [binding, min] = entries[0] ?? ['risk', 0]
  return { shares: Math.max(0, Math.floor(min)), riskPerShare: r, binding, caps }
}
