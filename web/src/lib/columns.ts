// Every screener column the site knows about. A column shows up once the pipeline exports its
// field; until then the column chooser lists it as "arrives in phase N".

export type ColumnKind =
  | 'text'
  | 'ticker'
  | 'price'
  | 'pct' // signed return, e.g. +12.3%
  | 'pctAbs' // unsigned share, e.g. 34.1%
  | 'prob' // probability 0..1 shown as 0-100%
  | 'score' // 0-100 family score
  | 'num'
  | 'money'
  | 'bool'
  | 'date'
  | 'label'

export type ColumnGroup =
  | 'Stock'
  | 'Decision'
  | 'Forecast'
  | 'Evidence'
  | 'Analysts'
  | 'Ownership'
  | 'Returns'
  | 'Risk'
  | 'Trend'
  | 'Size & liquidity'
  | 'Events'
  | 'Data'

export interface ColumnDef {
  key: string
  label: string
  group: ColumnGroup
  kind: ColumnKind
  /** What the number means, shown in the header tooltip. */
  help: string
  /** Build phase that adds the field. */
  phase: number
  defaultVisible?: boolean
  width?: number
}

const P = (horizon: string, what: string) =>
  `Chance the stock is ${what} after ${horizon}. RESEARCH MODE: not yet validated; until models are trained this is an uncalibrated estimate from expected return and volatility.`

export const COLUMNS: ColumnDef[] = [
  { key: 'ticker', label: 'Ticker', group: 'Stock', kind: 'ticker', help: 'Stock symbol.', phase: 1, defaultVisible: true, width: 84 },
  { key: 'name', label: 'Name', group: 'Stock', kind: 'text', help: 'Company name.', phase: 1, defaultVisible: true, width: 200 },
  { key: 'exchange', label: 'Exchange', group: 'Stock', kind: 'text', help: 'Listing exchange.', phase: 1, width: 110 },
  { key: 'sector', label: 'Sector', group: 'Stock', kind: 'text', help: 'Sector from the SEC industry code (SIC).', phase: 2, defaultVisible: true, width: 150 },
  { key: 'industry', label: 'Industry', group: 'Stock', kind: 'text', help: 'Industry description from the SEC (SIC).', phase: 2, width: 200 },
  { key: 'is_adr', label: 'ADR', group: 'Stock', kind: 'bool', help: 'American Depositary Receipt (a foreign company traded in the US).', phase: 1, width: 64 },

  { key: 'label', label: 'Label', group: 'Decision', kind: 'label', help: 'The decision label (STRONG BUY — TOP CONVICTION, BUY, WATCH, NO TRADE, SELL / RISK WARNING). Always check the numbers behind it on the stock page.', phase: 3, defaultVisible: true, width: 130 },
  { key: 'ev', label: 'EV', group: 'Decision', kind: 'pct', help: 'Expected value of the 60-day trade after costs: p·average win − (1−p)·average loss − costs. RESEARCH MODE.', phase: 3, width: 84 },
  { key: 'gain_per_month', label: 'Gain / month', group: 'Decision', kind: 'pct', help: 'Expected gain per month (median 6-month forecast ÷ 6). RESEARCH MODE.', phase: 3, defaultVisible: true, width: 100 },
  { key: 'speed', label: 'Speed', group: 'Decision', kind: 'num', help: 'Expected gain per month divided by volatility per month. Higher = more expected gain per unit of risk, per month.', phase: 3, width: 76 },

  { key: 'p_up_1w', label: 'P(up) 1w', group: 'Forecast', kind: 'prob', help: P('1 week (5 trading days)', 'higher'), phase: 3, width: 88 },
  { key: 'p_up_1m', label: 'P(up) 1m', group: 'Forecast', kind: 'prob', help: P('1 month (21 trading days)', 'higher'), phase: 3, width: 88 },
  { key: 'p_up_3m', label: 'P(up) 3m', group: 'Forecast', kind: 'prob', help: P('3 months (63 trading days)', 'higher'), phase: 3, width: 88 },
  { key: 'p_up_6m', label: 'P(up) 6m', group: 'Forecast', kind: 'prob', help: P('6 months (126 trading days)', 'higher'), phase: 3, defaultVisible: true, width: 88 },
  { key: 'p_beat_6m', label: 'P(beat) 6m', group: 'Forecast', kind: 'prob', help: P('6 months', 'ahead of the S&P 500 (total return)'), phase: 3, width: 96 },
  { key: 'med_6m', label: 'Median 6m', group: 'Forecast', kind: 'pct', help: 'Median 6-month forecast return. Half of outcomes are expected above, half below. RESEARCH MODE.', phase: 3, width: 96 },
  { key: 'p90_6m', label: '90th pct 6m', group: 'Forecast', kind: 'pct', help: 'Optimistic scenario: only 1 in 10 outcomes is expected above this 6-month return. RESEARCH MODE.', phase: 3, width: 100 },

  { key: 'f1', label: 'F1 Opinion', group: 'Evidence', kind: 'score', help: 'Analyst and rating-platform opinion, beyond what revisions and momentum already say. 0–100, 50 = sector median.', phase: 3, width: 92 },
  { key: 'f2', label: 'F2 Revisions', group: 'Evidence', kind: 'score', help: 'Earnings-estimate revisions over 60 days. 0–100, 50 = sector median.', phase: 3, width: 100 },
  { key: 'f3', label: 'F3 Earnings', group: 'Evidence', kind: 'score', help: 'Earnings surprise and reaction. 0–100, 50 = sector median.', phase: 3, width: 96 },
  { key: 'f4', label: 'F4 Insiders', group: 'Evidence', kind: 'score', help: 'Opportunistic insider buying and ownership. 0–100, 50 = sector median.', phase: 3, width: 92 },
  { key: 'f5', label: 'F5 Trend', group: 'Evidence', kind: 'score', help: 'Stock-specific momentum and trend. 0–100, 50 = sector median.', phase: 3, width: 84 },
  { key: 'f6', label: 'F6 Quality', group: 'Evidence', kind: 'score', help: 'Profitability, cash flow and balance-sheet quality from SEC filings. 0–100, 50 = sector median.', phase: 3, width: 92 },
  { key: 'n_eff', label: 'N_eff', group: 'Evidence', kind: 'num', help: 'Effective number of independent bullish evidence families (correlated families count less).', phase: 3, width: 70 },
  { key: 'disagreement', label: 'D', group: 'Evidence', kind: 'num', help: 'Disagreement: standard deviation of the six family scores. Lower = families agree.', phase: 3, width: 60 },

  { key: 'consensus', label: 'Consensus', group: 'Analysts', kind: 'num', help: 'Analyst consensus on a 1 (strong buy) to 5 (strong sell) scale.', phase: 2, width: 96 },
  { key: 'n_analysts', label: '# Analysts', group: 'Analysts', kind: 'num', help: 'Number of analysts with an opinion.', phase: 2, width: 90 },
  { key: 'target_upside', label: 'Target upside', group: 'Analysts', kind: 'pct', help: 'Mean analyst price target ÷ price − 1. Analysts are often too optimistic.', phase: 2, defaultVisible: true, width: 108 },
  { key: 'rev60', label: 'EPS rev. 60d', group: 'Analysts', kind: 'pct', help: 'Change in this fiscal year’s EPS estimate over the last 60 days.', phase: 2, width: 100 },

  { key: 'insider_net_90d', label: 'Insider buys 90d', group: 'Ownership', kind: 'money', help: 'Dollar value of opportunistic open-market insider purchases in the last 90 days (routine and 10b5-1 plan trades excluded).', phase: 2, width: 120 },
  { key: 'short_pct_float', label: 'Short % float', group: 'Ownership', kind: 'pctAbs', help: 'Shares sold short as a share of the float (FINRA / exchange data, twice monthly).', phase: 2, width: 104 },
  { key: 'days_to_cover', label: 'Days to cover', group: 'Ownership', kind: 'num', help: 'Short interest ÷ average daily volume.', phase: 2, width: 100 },
  { key: 'iv_30d', label: 'Implied vol', group: 'Ownership', kind: 'pctAbs', help: 'Options-implied volatility (about 30 days, annualized).', phase: 2, width: 96 },

  { key: 'price', label: 'Price', group: 'Returns', kind: 'price', help: 'Last close (split-adjusted).', phase: 1, defaultVisible: true, width: 90 },
  { key: 'change_1d', label: '1d', group: 'Returns', kind: 'pct', help: 'Total return on the last trading day.', phase: 1, width: 72 },
  { key: 'ret_1w', label: '1w', group: 'Returns', kind: 'pct', help: 'Total return over 5 trading days (dividends included).', phase: 1, width: 72 },
  { key: 'ret_1m', label: '1m', group: 'Returns', kind: 'pct', help: 'Total return over 21 trading days.', phase: 1, defaultVisible: true, width: 72 },
  { key: 'ret_3m', label: '3m', group: 'Returns', kind: 'pct', help: 'Total return over 63 trading days.', phase: 1, width: 72 },
  { key: 'ret_ytd', label: 'YTD', group: 'Returns', kind: 'pct', help: 'Total return since the last close of the previous year.', phase: 1, width: 76 },
  { key: 'ret_1y', label: '1y', group: 'Returns', kind: 'pct', help: 'Total return over 252 trading days.', phase: 1, defaultVisible: true, width: 76 },

  { key: 'vol_63', label: 'Volatility', group: 'Risk', kind: 'pctAbs', help: 'Annualized volatility of daily returns over the last 63 trading days.', phase: 1, width: 88 },
  { key: 'atr_pct', label: 'ATR %', group: 'Risk', kind: 'pctAbs', help: 'Average true range (14 days) as a share of price: a typical daily move.', phase: 1, width: 76 },

  { key: 'trend_up', label: 'Uptrend', group: 'Trend', kind: 'bool', help: 'Price above its 50-day average, which is above its 200-day average.', phase: 1, width: 80 },
  { key: 'dist_52w_high', label: 'From 52w high', group: 'Trend', kind: 'pct', help: 'Distance below the highest price of the last 52 weeks.', phase: 1, width: 108 },

  { key: 'market_cap', label: 'Market cap', group: 'Size & liquidity', kind: 'money', help: 'Shares outstanding (SEC filings) × price.', phase: 2, width: 100 },
  { key: 'adv_dollar', label: 'Avg $ volume', group: 'Size & liquidity', kind: 'money', help: 'Average daily traded value over 21 days. Signals need at least $10M and a price of at least $5.', phase: 1, width: 104 },
  { key: 'eligible', label: 'Eligible', group: 'Size & liquidity', kind: 'bool', help: 'Price ≥ $5, average daily traded value ≥ $10M and priced on the last session. Only eligible stocks can get BUY labels.', phase: 1, width: 80 },

  { key: 'next_earnings', label: 'Next earnings', group: 'Events', kind: 'date', help: 'Next expected earnings report date.', phase: 2, width: 110 },

  { key: 'last_date', label: 'Data as of', group: 'Data', kind: 'date', help: 'Date of the last price used.', phase: 1, width: 96 },
]

export const COLUMN_BY_KEY: Record<string, ColumnDef> = Object.fromEntries(COLUMNS.map((c) => [c.key, c]))

export const GROUP_ORDER: ColumnGroup[] = [
  'Stock',
  'Decision',
  'Forecast',
  'Evidence',
  'Analysts',
  'Ownership',
  'Returns',
  'Risk',
  'Trend',
  'Size & liquidity',
  'Events',
  'Data',
]
