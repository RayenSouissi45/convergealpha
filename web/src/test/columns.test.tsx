import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { findBucket, renderCell } from '../lib/cells'
import { COLUMN_DOCS, statusText } from '../lib/columnDocs'
import { COLUMNS, COLUMN_BY_KEY, forecastColumns, GROUP_ORDER, HORIZONS } from '../lib/columns'
import { zeroCounts, zeroKeep } from '../lib/zero'
import type { ReliabilityTables, ScreenerRow } from '../types'

const PARTS = ['name', 'what', 'how', 'example', 'read', 'source', 'mistakes'] as const

describe('column explanations', () => {
  it('every column in the registry has all 8 parts of its explanation', () => {
    const missing: string[] = []
    for (const c of COLUMNS) {
      const doc = COLUMN_DOCS[c.key]
      if (!doc) {
        missing.push(`${c.key}: no explanation`)
        continue
      }
      for (const part of PARTS) {
        if (typeof doc[part] !== 'string' || doc[part].trim().length < 3) missing.push(`${c.key}: ${part}`)
      }
      if (!doc.status) missing.push(`${c.key}: status`)
    }
    expect(missing).toEqual([])
  })

  it('has no explanation for a column that does not exist', () => {
    expect(Object.keys(COLUMN_DOCS).filter((k) => !COLUMN_BY_KEY[k])).toEqual([])
  })

  it('covers every column the owner listed, in the agreed groups', () => {
    const wanted = [
      'ticker', 'name', 'sector', 'industry', 'label', 'tier', 'eligible', 'blocked', 'ev', 'p_hat', 'gain_per_month', 'speed',
      ...HORIZONS.flatMap((h) => [`p_up_${h}`, `p_beat_${h}`, `p10_${h}`, `p90_${h}`, `med_${h}`, `hit_up_${h}`]),
      'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'n_eff', 'disagreement', 'consensus', 'n_analysts', 'target_upside', 'rev60',
      'insider_buy_7d', 'insider_net_90d', 'short_pct_float', 'days_to_cover', 'iv_30d', 'price',
      'change_1d', 'ret_1w', 'ret_1m', 'ret_3m', 'ret_ytd', 'ret_1y', 'vol_63', 'atr_pct', 'trend_up', 'dist_52w_high',
      'market_cap', 'adv_dollar', 'next_earnings', 'days_to_earnings', 'cluster', 'zero',
    ]
    expect(wanted.filter((k) => !COLUMN_BY_KEY[k])).toEqual([])
    expect(GROUP_ORDER).toEqual(['Basics', 'Label & decision', 'Forecasts', 'Evidence families', 'Analysts', 'Insiders', 'Risk', 'Past performance', 'Size & liquidity', 'Events'])
    expect(COLUMNS.every((c) => GROUP_ORDER.includes(c.group))).toBe(true)
  })

  it('says per horizon whether a probability is validated', () => {
    const v = ['P(up) 6m']
    expect(statusText(COLUMN_DOCS.p_up_6m!, v).validated).toBe(true)
    expect(statusText(COLUMN_DOCS.p_up_1w!, v).validated).toBe(false)
    expect(statusText(COLUMN_DOCS.p_up_1w!, v).text).toMatch(/RESEARCH MODE/)
    expect(statusText(COLUMN_DOCS.price!, v).validated).toBeNull()
    expect(statusText(COLUMN_DOCS.hit_up_6m!, v).text).toMatch(/✓/)
  })
})

const TABLES: ReliabilityTables = {
  up: {
    '6m': [
      { lo: 0, hi: 0.55, n: 5000, rate: 0.53, wilson_lo: 0.516, wilson_hi: 0.544 },
      { lo: 0.55, hi: 1.01, n: 400, rate: 0.57, wilson_lo: 0.521, wilson_hi: 0.618 },
    ],
  },
}

function cell(key: string, row: ScreenerRow, validated: string[] = []) {
  return render(<MemoryRouter>{renderCell(key, row[key] ?? null, undefined, { row, reliability: TABLES, validated })}</MemoryRouter>)
}

describe('forecast columns', () => {
  const row: ScreenerRow = { ticker: 'X', med_6m: 0.018, p10_6m: -0.06, p90_6m: 0.09, p_up_6m: 0.58, hit_up_6m: 0.57, p_up_1w: 0.47 }

  it('show the expected change with its 80% range', () => {
    const { container } = cell('med_6m', row)
    expect(container).toHaveTextContent('+1.8%')
    expect(container).toHaveTextContent('−6% to +9%')
  })

  it('colour chances: green above 50%, red below, with the number always shown', () => {
    expect(cell('p_up_6m', row).container.querySelector('span')?.className).toMatch(/emerald/)
    expect(cell('p_up_1w', row).container.querySelector('span')?.className).toMatch(/red/)
  })

  it('show how often similar calls were right, its ± range, and ✓ only when validated', () => {
    let c = cell('hit_up_6m', row, ['P(up) 6m']).container
    expect(c).toHaveTextContent('57% ±5%')
    expect(c).toHaveTextContent('✓ validated')
    c = cell('hit_up_6m', row, []).container
    expect(c).toHaveTextContent('research')
  })

  it('find the same bucket as the pipeline ([lo, hi) edges)', () => {
    expect(findBucket(TABLES.up['6m'], 0.55)?.rate).toBe(0.57)
    expect(findBucket(TABLES.up['6m'], 0.5499)?.rate).toBe(0.53)
    expect(findBucket(TABLES.up['6m'], null)).toBeNull()
  })

  it('missing values stay "—" with a reason', () => {
    cell('hit_up_6m', { ticker: 'Y' })
    expect(screen.getByRole('button', { name: /Not available: No past record/ })).toHaveTextContent('—')
  })

  it('the Forecast view has 3 columns per horizon', () => {
    expect(HORIZONS.flatMap((h) => forecastColumns(h))).toHaveLength(12)
    expect(forecastColumns('1m')).toEqual(['med_1m', 'p_up_1m', 'hit_up_1m'])
  })
})

describe('finanzen.net zero values', () => {
  it('unknown is never treated as not buyable', () => {
    expect(zeroKeep(true, true)).toBe(true)
    expect(zeroKeep(null, true)).toBe(true)
    expect(zeroKeep(undefined, true)).toBe(true)
    expect(zeroKeep(false, true)).toBe(false)
    expect(zeroKeep(false, false)).toBe(true)
    expect(zeroCounts([true, false, null, true, undefined])).toEqual({ yes: 2, no: 1, unknown: 2 })
  })

  it('the zero column says Yes, No or ?', () => {
    expect(cell('zero', { ticker: 'A', zero: true }).container).toHaveTextContent('Yes')
    expect(cell('zero', { ticker: 'B', zero: false }).container).toHaveTextContent('No')
    expect(cell('zero', { ticker: 'C', zero: null }).container).toHaveTextContent('?')
  })
})
