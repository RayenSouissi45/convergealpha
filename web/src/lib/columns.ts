// Every screener column the site knows about. A column shows up once the pipeline exports its
// field; until then the column chooser lists it as "arrives in phase N". Each column has a full
// explanation in columnDocs.ts (a test fails if one is missing).

export type ColumnKind =
  | 'text'
  | 'ticker'
  | 'price'
  | 'pct' // signed return, e.g. +12.3%
  | 'pctAbs' // unsigned share, e.g. 34.1%
  | 'prob' // probability 0..1 shown as 0-100%
  | 'score' // 0-100 family score
  | 'num'
  | 'int'
  | 'money'
  | 'bool'
  | 'date'
  | 'label'
  | 'forecast' // median forecast return with its 80% range (p10 to p90) as a second line
  | 'hit' // past hit rate of the "chance up" bucket, with its range and validation mark
  | 'zero' // buyable on finanzen.net zero: yes / no / not sure
  | 'opp' // opportunity badge: green / amber / red, with a "Why?" panel

export type ColumnGroup =
  | 'Basics'
  | 'Label & decision'
  | 'Forecasts'
  | 'Evidence families'
  | 'Analysts'
  | 'Insiders'
  | 'Risk'
  | 'Past performance'
  | 'Size & liquidity'
  | 'Events'

export interface ColumnDef {
  key: string
  /** Header text: complete words, wraps to two lines. */
  label: string
  group: ColumnGroup
  kind: ColumnKind
  /** One short sentence (filter editor and fallbacks). The full explanation is in columnDocs.ts. */
  help: string
  /** Build phase that adds the field. */
  phase: number
  defaultVisible?: boolean
  width?: number
}

export const HORIZONS = ['1w', '1m', '3m', '6m'] as const
export type HorizonKey = (typeof HORIZONS)[number]
export const H_SHORT: Record<HorizonKey, string> = { '1w': '1W', '1m': '1M', '3m': '3M', '6m': '6M' }
export const H_LONG: Record<HorizonKey, string> = { '1w': '1 week', '1m': '1 month', '3m': '3 months', '6m': '6 months' }

/** Validation status appended to probability tooltips (from health.json). */
export function probabilityStatus(key: string, validated: string[], method: string | undefined): string {
  const m = key.match(/^(?:p|hit)_(up|beat)_(1w|1m|3m|6m)$/)
  if (!m) return ''
  const ok = validated.includes(`P(${m[1]}) ${m[2]}`)
  const how = method === 'model' ? 'Calibrated walk-forward model.' : 'Fallback estimate from expected return and volatility (not calibrated).'
  return ` ${ok ? 'Validated on the 2024–2026 holdout.' : 'RESEARCH MODE: not yet validated.'} ${how}`
}

const horizonColumns: ColumnDef[] = HORIZONS.flatMap((h): ColumnDef[] => [
  { key: `med_${h}`, label: `Expected change ${H_SHORT[h]}`, group: 'Forecasts', kind: 'forecast', help: `Median forecast return after ${H_LONG[h]}, with the 80% range below it.`, phase: 3, defaultVisible: h === '6m', width: 112 },
  { key: `p_up_${h}`, label: `Chance up ${H_SHORT[h]}`, group: 'Forecasts', kind: 'prob', help: `Chance the price is higher after ${H_LONG[h]}.`, phase: 3, defaultVisible: h === '6m', width: 92 },
  { key: `hit_up_${h}`, label: `How often right ${H_SHORT[h]}`, group: 'Forecasts', kind: 'hit', help: `How often stocks with a similar "chance up" were really higher after ${H_LONG[h]}.`, phase: 4, width: 108 },
  { key: `p_beat_${h}`, label: `Chance to beat S&P ${H_SHORT[h]}`, group: 'Forecasts', kind: 'prob', help: `Chance the stock does better than the S&P 500 over ${H_LONG[h]}.`, phase: 3, width: 104 },
  { key: `p10_${h}`, label: `Bad case ${H_SHORT[h]}`, group: 'Forecasts', kind: 'pct', help: `Pessimistic ${H_LONG[h]} outcome: only 1 in 10 outcomes is expected below it.`, phase: 3, width: 92 },
  { key: `p90_${h}`, label: `Good case ${H_SHORT[h]}`, group: 'Forecasts', kind: 'pct', help: `Optimistic ${H_LONG[h]} outcome: only 1 in 10 outcomes is expected above it.`, phase: 3, width: 92 },
])

export const COLUMNS: ColumnDef[] = [
  { key: 'ticker', label: 'Ticker', group: 'Basics', kind: 'ticker', help: 'Stock symbol.', phase: 1, defaultVisible: true, width: 84 },
  { key: 'name', label: 'Name', group: 'Basics', kind: 'text', help: 'Company name.', phase: 1, defaultVisible: true, width: 200 },
  { key: 'zero', label: 'On finanzen.net zero', group: 'Basics', kind: 'zero', help: 'Can be bought at the broker finanzen.net zero (via gettex).', phase: 7, width: 104 },
  { key: 'exchange', label: 'Exchange', group: 'Basics', kind: 'text', help: 'Listing exchange.', phase: 1, width: 110 },
  { key: 'sector', label: 'Sector', group: 'Basics', kind: 'text', help: 'Sector from the SEC industry code (SIC).', phase: 2, defaultVisible: true, width: 150 },
  { key: 'industry', label: 'Industry', group: 'Basics', kind: 'text', help: 'Industry description from the SEC (SIC).', phase: 2, width: 200 },
  { key: 'is_adr', label: 'ADR', group: 'Basics', kind: 'bool', help: 'American Depositary Receipt (a foreign company traded in the US).', phase: 1, width: 72 },
  { key: 'price', label: 'Price', group: 'Basics', kind: 'price', help: 'Last close (split-adjusted).', phase: 1, defaultVisible: true, width: 90 },
  { key: 'last_date', label: 'Data as of', group: 'Basics', kind: 'date', help: 'Date of the last price used.', phase: 1, width: 104 },

  { key: 'label', label: 'Label', group: 'Label & decision', kind: 'label', help: 'The decision label. Always check the numbers behind it on the stock page.', phase: 3, defaultVisible: true, width: 130 },
  { key: 'tier', label: 'Tier', group: 'Label & decision', kind: 'int', help: 'Position size tier for BUY labels: 1 = full size, 2 = half size.', phase: 3, width: 72 },
  { key: 'eligible', label: 'Eligible', group: 'Label & decision', kind: 'bool', help: 'Price ≥ $5 and ≥ $10M traded per day: only eligible stocks can get BUY labels.', phase: 1, width: 88 },
  { key: 'blocked', label: 'Blocked', group: 'Label & decision', kind: 'bool', help: 'An event (earnings soon, offering, merger…) blocks new entries.', phase: 3, width: 84 },
  { key: 'block_reason', label: 'Blocking event', group: 'Label & decision', kind: 'text', help: 'The first blocking event.', phase: 3, width: 200 },
  { key: 'opp', label: 'Opportunity', group: 'Label & decision', kind: 'opp', help: 'Opportunity badge: confirmed (green), possible (amber) or hype / be careful (red). Tap “Why?”.', phase: 8, defaultVisible: true, width: 150 },
  { key: 'ev', label: 'Expected value', group: 'Label & decision', kind: 'pct', help: 'Expected gain of the 60-day trade after costs.', phase: 3, width: 96 },
  { key: 'p_hat', label: 'Chance trade works (p̂)', group: 'Label & decision', kind: 'prob', help: 'Chance the 60-day trade ends ahead of the S&P 500 after costs.', phase: 3, width: 112 },
  { key: 'gain_per_month', label: 'Gain per month', group: 'Label & decision', kind: 'pct', help: 'Median 6-month forecast divided by 6.', phase: 3, defaultVisible: true, width: 96 },
  { key: 'speed', label: 'Speed', group: 'Label & decision', kind: 'num', help: 'Expected gain per month divided by monthly volatility.', phase: 3, width: 84 },

  ...horizonColumns,

  { key: 'f1', label: 'F1 Opinion', group: 'Evidence families', kind: 'score', help: 'Analyst and rating opinion score, 0–100 within the sector.', phase: 3, width: 92 },
  { key: 'f2', label: 'F2 Revisions', group: 'Evidence families', kind: 'score', help: 'Earnings-estimate revisions score, 0–100 within the sector.', phase: 3, width: 100 },
  { key: 'f3', label: 'F3 Earnings', group: 'Evidence families', kind: 'score', help: 'Earnings surprise score, 0–100 within the sector.', phase: 3, width: 96 },
  { key: 'f4', label: 'F4 Insiders', group: 'Evidence families', kind: 'score', help: 'Insider buying score, 0–100 within the sector.', phase: 3, width: 92 },
  { key: 'f5', label: 'F5 Trend', group: 'Evidence families', kind: 'score', help: 'Price trend score, 0–100 within the sector.', phase: 3, width: 84 },
  { key: 'f6', label: 'F6 Quality', group: 'Evidence families', kind: 'score', help: 'Business quality score, 0–100 within the sector.', phase: 3, width: 92 },
  { key: 'n_eff', label: 'Independent evidence (N_eff)', group: 'Evidence families', kind: 'num', help: 'How many independent families are bullish.', phase: 3, width: 116 },
  { key: 'disagreement', label: 'Disagreement (D)', group: 'Evidence families', kind: 'num', help: 'How much the six family scores disagree.', phase: 3, width: 112 },

  { key: 'consensus', label: 'Analyst consensus', group: 'Analysts', kind: 'num', help: 'Average analyst rating, 1 = strong buy … 5 = strong sell.', phase: 2, width: 100 },
  { key: 'n_analysts', label: 'Analysts', group: 'Analysts', kind: 'int', help: 'Number of analysts with a rating.', phase: 2, width: 88 },
  { key: 'target_upside', label: 'Target upside', group: 'Analysts', kind: 'pct', help: 'Average analyst price target versus today’s price.', phase: 2, defaultVisible: true, width: 96 },
  { key: 'rev60', label: 'EPS revisions 60 days', group: 'Analysts', kind: 'pct', help: 'Change in this year’s earnings estimate over 60 days.', phase: 2, width: 112 },

  { key: 'insider_buy_7d', label: 'Insider buys 7 days', group: 'Insiders', kind: 'money', help: 'Opportunistic insider purchases filed in the last 7 days.', phase: 3, width: 104 },
  { key: 'insider_net_90d', label: 'Insider buys 90 days', group: 'Insiders', kind: 'money', help: 'Opportunistic insider purchases in the last 90 days.', phase: 2, width: 104 },

  { key: 'vol_63', label: 'Volatility', group: 'Risk', kind: 'pctAbs', help: 'How much the price moves, per year (last 3 months).', phase: 1, width: 96 },
  { key: 'atr_pct', label: 'Daily range (ATR)', group: 'Risk', kind: 'pctAbs', help: 'Typical daily move as a share of the price.', phase: 1, width: 96 },
  { key: 'short_pct_float', label: 'Short interest', group: 'Risk', kind: 'pctAbs', help: 'Shares sold short as a share of the tradable shares.', phase: 2, width: 96 },
  { key: 'days_to_cover', label: 'Days to cover', group: 'Risk', kind: 'num', help: 'Short interest divided by average daily volume.', phase: 2, width: 96 },
  { key: 'iv_30d', label: 'Implied volatility', group: 'Risk', kind: 'pctAbs', help: 'Volatility the options market expects (about 30 days).', phase: 2, width: 100 },
  { key: 'cluster', label: 'Correlation group', group: 'Risk', kind: 'int', help: 'Stocks that move closely together share a group number.', phase: 3, width: 104 },

  { key: 'change_1d', label: 'Return 1 day', group: 'Past performance', kind: 'pct', help: 'Total return on the last trading day.', phase: 1, width: 84 },
  { key: 'ret_1w', label: 'Return 1 week', group: 'Past performance', kind: 'pct', help: 'Total return over 5 trading days.', phase: 1, width: 84 },
  { key: 'ret_1m', label: 'Return 1 month', group: 'Past performance', kind: 'pct', help: 'Total return over 21 trading days.', phase: 1, defaultVisible: true, width: 88 },
  { key: 'ret_3m', label: 'Return 3 months', group: 'Past performance', kind: 'pct', help: 'Total return over 63 trading days.', phase: 1, width: 88 },
  { key: 'ret_ytd', label: 'Return this year', group: 'Past performance', kind: 'pct', help: 'Total return since the end of last year.', phase: 1, width: 88 },
  { key: 'ret_1y', label: 'Return 1 year', group: 'Past performance', kind: 'pct', help: 'Total return over 252 trading days.', phase: 1, defaultVisible: true, width: 84 },
  { key: 'trend_up', label: 'Uptrend', group: 'Past performance', kind: 'bool', help: 'Price above its 50-day average, which is above its 200-day average.', phase: 1, width: 88 },
  { key: 'dist_52w_high', label: 'From 52-week high', group: 'Past performance', kind: 'pct', help: 'How far below the highest price of the last 52 weeks.', phase: 1, width: 96 },

  { key: 'market_cap', label: 'Market cap', group: 'Size & liquidity', kind: 'money', help: 'Company value: shares outstanding × price.', phase: 2, width: 96 },
  { key: 'adv_dollar', label: 'Dollar volume per day', group: 'Size & liquidity', kind: 'money', help: 'Average value traded per day (21 days).', phase: 1, width: 104 },

  { key: 'next_earnings', label: 'Next earnings', group: 'Events', kind: 'date', help: 'Next expected earnings report date.', phase: 2, width: 108 },
  { key: 'opp_event', label: 'Opportunity event', group: 'Events', kind: 'text', help: 'The main fresh event behind the opportunity badge, with its date.', phase: 8, width: 190 },
  { key: 'days_to_earnings', label: 'Days to earnings', group: 'Events', kind: 'int', help: 'Trading days until the next report.', phase: 2, width: 96 },
]

export const COLUMN_BY_KEY: Record<string, ColumnDef> = Object.fromEntries(COLUMNS.map((c) => [c.key, c]))

export const GROUP_ORDER: ColumnGroup[] = [
  'Basics',
  'Label & decision',
  'Forecasts',
  'Evidence families',
  'Analysts',
  'Insiders',
  'Risk',
  'Past performance',
  'Size & liquidity',
  'Events',
]

/** The three Forecast-view columns of one horizon, in display order. */
export function forecastColumns(h: HorizonKey): string[] {
  return [`med_${h}`, `p_up_${h}`, `hit_up_${h}`]
}
