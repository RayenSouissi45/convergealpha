// Plain-English explanation of every screener column, for the (i) tooltips and the
// "Columns explained" page. Short sentences, simple words: many readers are not native English
// speakers and not finance experts. A test checks that every column in COLUMNS has all 8 parts.

import { H_LONG, HORIZONS, type HorizonKey } from './columns'

export type DocStatus =
  | { kind: 'data' } // a measured fact, not a forecast
  | { kind: 'research' } // app output that has not passed the validation lab
  | { kind: 'horizon'; promise: 'up' | 'beat'; h: HorizonKey } // passes or not, per horizon
  | { kind: 'record'; h: HorizonKey } // the past hit-rate record itself

export interface ColumnDoc {
  /** 1. Plain-English name. */
  name: string
  /** 2. What it means, in 1–2 simple sentences. */
  what: string
  /** 3. How it is calculated, as a formula in words. */
  how: string
  /** 4. Units and a concrete example. */
  example: string
  /** 5. What is good and what is bad, with typical ranges. */
  read: string
  /** 6. Data source and how often it updates. */
  source: string
  /** 7. Validated or still RESEARCH MODE. */
  status: DocStatus
  /** 8. Common mistakes when reading it. */
  mistakes: string
}

const PRICES = 'Daily prices from Yahoo Finance. Updated every weekday after the US market closes.'
const SEC = 'SEC EDGAR company records (the official US filings database). Checked every day, refreshed at least monthly.'
const ANALYSTS = 'Yahoo Finance analyst data. Refreshed about once a week for every stock, and every day for about 400 candidates, your holdings and stocks near earnings.'
const MODEL = 'The app’s own models. Retrained every Saturday on data since 2012, applied after every daily close.'
const RULES = 'The app’s decision rules, recomputed after every daily close.'
const FAMILIES_SRC = 'Computed by the app after every daily close from its data sources (see the Health page).'
const INSIDERS = 'SEC Form 4 filings (insiders must report trades within 2 business days). Updated every weekday.'
const FINRA = 'FINRA short-interest files, published twice a month (about 8 trading days after the settlement date).'
const NOT_FORECAST = 'This is a measured number, not a forecast.'

const horizonDocs: Record<string, ColumnDoc> = Object.fromEntries(
  HORIZONS.flatMap((h): [string, ColumnDoc][] => {
    const long = H_LONG[h]
    const days = { '1w': 5, '1m': 21, '3m': 63, '6m': 126 }[h]
    return [
      [
        `med_${h}`,
        {
          name: `Expected change, ${long}`,
          what: `The middle forecast for the price change over the next ${long}. Below it is the 80% range: 8 out of 10 outcomes are expected inside it.`,
          how: `The median of the model's forecast of the total return (price change plus dividends) over ${days} trading days. The range is the 10th to the 90th percentile forecast, widened so that 80% of past outcomes fell inside it.`,
          example: `"+1.8%" with "−6% to +9%" below means: the middle outcome is a 1.8% gain, and 8 times out of 10 the change should be between a 6% loss and a 9% gain.`,
          read: `Higher is better, but the range matters as much: a wide range means a risky stock. Typical medians are small: −2% to +3% for ${long === '1 week' ? 'a week' : long}${h === '6m' ? ', −10% to +15% for 6 months' : ''}.`,
          source: MODEL,
          status: { kind: 'research' },
          mistakes: 'It is not a price target and not a promise. Half of the outcomes are expected below it, and 1 in 10 below the range.',
        },
      ],
      [
        `p_up_${h}`,
        {
          name: `Chance up, ${long}`,
          what: `The chance that the stock is higher (with dividends) after ${long} than at today's close.`,
          how: `A model estimates the chance from the stock's evidence, then a calibration step adjusts it so that, in past data, about X% of stocks with "X%" really went up.`,
          example: `"58%" means: in the past, about 58 of 100 stocks with this kind of evidence were higher after ${long}.`,
          read: `Above 50% leans up, below 50% leans down. Most stocks are between 45% and 65%. Values above 60% are rare.`,
          source: MODEL,
          status: { kind: 'horizon', promise: 'up', h },
          mistakes: '58% is not a sure thing: 42 of 100 such stocks went down. "Higher" does not mean "better than the market" (see Chance to beat S&P).',
        },
      ],
      [
        `hit_up_${h}`,
        {
          name: `How often right, ${long}`,
          what: `When the app gave a "chance up" like this stock's in the past, how often was the stock really higher after ${long}?`,
          how: `Past predictions are grouped by their chance (for example 55–58%). For the group this stock falls into: hit rate = stocks that were really higher ÷ all stocks in the group. The ± is the 95% Wilson range. Only out-of-sample predictions from 2016–2023 are used, and each year was calibrated without its own outcomes.`,
          example: `"57% ±2%" means: of the past cases with a similar chance, 57% were higher after ${long}, and the true rate is probably between 55% and 59%. The tooltip and the stock page show how many cases (n).`,
          read: `Close to the "chance up" = the app was honest for such stocks. Much lower = it was too optimistic. Each group has at least 200 cases. ✓ means this horizon also passed the holdout test (2024–2026).`,
          source: 'The weekly model job (Saturdays), from the walk-forward history of the models.',
          status: { kind: 'record', h },
          mistakes: 'Past cases overlap in time and stocks move together, so the real uncertainty is wider than the ± shown. A good past record does not guarantee the future.',
        },
      ],
      [
        `p_beat_${h}`,
        {
          name: `Chance to beat the S&P 500, ${long}`,
          what: `The chance that the stock does better than the S&P 500 index (both with dividends) over the next ${long}.`,
          how: `Same method as "Chance up", but the outcome is: stock return minus S&P 500 return is above zero.`,
          example: `"48%" means: slightly less than an even chance to do better than the market over ${long}.`,
          read: 'Above 50% = expected to beat the market. Most stocks are between 40% and 55%: beating the market is hard.',
          source: MODEL,
          status: { kind: 'horizon', promise: 'beat', h },
          mistakes: 'A stock can go up and still lose to the market. This is a harder promise than "Chance up".',
        },
      ],
      [
        `p10_${h}`,
        {
          name: `Bad case, ${long}`,
          what: `A pessimistic outcome for the next ${long}: only 1 in 10 outcomes is expected to be worse.`,
          how: `The 10th percentile of the model's return forecast over ${days} trading days, widened so that past outcomes fell inside the 80% range 8 times out of 10.`,
          example: `"−12%" means: there is about a 1 in 10 chance of losing 12% or more over ${long}.`,
          read: 'Closer to zero is safer. Very negative values (for example below −30% for 6 months) mean a risky stock.',
          source: MODEL,
          status: { kind: 'research' },
          mistakes: 'It is not the worst case. Losses can be bigger, especially after bad news or earnings.',
        },
      ],
      [
        `p90_${h}`,
        {
          name: `Good case, ${long}`,
          what: `An optimistic outcome for the next ${long}: only 1 in 10 outcomes is expected to be better.`,
          how: `The 90th percentile of the model's return forecast over ${days} trading days, widened like the bad case.`,
          example: `"+25%" means: about a 1 in 10 chance of gaining 25% or more over ${long}.`,
          read: 'Higher means more upside, but usually also more risk: compare it with the bad case.',
          source: MODEL,
          status: { kind: 'research' },
          mistakes: 'Do not plan with the good case. It happens only 1 time in 10.',
        },
      ],
    ]
  }),
)

const familyDoc = (id: string, name: string, what: string, how: string, src: string): ColumnDoc => ({
  name: `${id.toUpperCase()} ${name} score`,
  what,
  how: `${how} The result is ranked within the stock's sector: 0 = weakest, 100 = strongest, 50 = sector median.`,
  example: `"${id.toUpperCase()} 82" means this stock is stronger on this evidence than about 82% of its sector.`,
  read: '60 or more is strong (BUY needs four families at 60+). 40 or less is weak. Missing ("—") means no fresh data.',
  source: src,
  status: { kind: 'research' },
  mistakes: 'A score compares with the sector, not with the whole market. One strong family alone is weak evidence: look at N_eff and the other families.',
})

export const COLUMN_DOCS: Record<string, ColumnDoc> = {
  ticker: {
    name: 'Ticker',
    what: 'The short code of the stock on the US exchange.',
    how: 'Taken as published by the exchange. Share classes use a dash, for example BRK-B.',
    example: 'AAPL is Apple Inc.',
    read: 'Not good or bad. Tap it to open the stock page. "n/e" after it means not eligible for signals.',
    source: 'SEC company list and Nasdaq Trader symbol files, refreshed every day.',
    status: { kind: 'data' },
    mistakes: 'Different share classes of one company (GOOG and GOOGL) are different stocks with different tickers.',
  },
  name: {
    name: 'Company name',
    what: 'The name of the company and the type of share.',
    how: 'As listed by the exchange.',
    example: '"Apple Inc. - Common Stock".',
    read: 'Not good or bad.',
    source: 'Nasdaq Trader symbol files, refreshed every day.',
    status: { kind: 'data' },
    mistakes: 'Similar names can be different companies: check the ticker.',
  },
  zero: {
    name: 'On finanzen.net zero',
    what: 'Whether you can buy this exact stock at the German broker finanzen.net zero.',
    how: 'finanzen.net zero trades only on gettex (Börse München). The app takes gettex’s official list of shares and ADRs from ESMA’s FIRDS register and maps each ISIN to a US ticker with OpenFIGI. Yes = on the list. No = not on the list. ? = not sure.',
    example: '"Yes" for AAPL: Apple shares can be bought there. "?" for a stock listed in the US less than 30 days ago.',
    read: 'Yes means buyable. "?" is not the same as "No": the app could not check it (new listing, or the list is missing or older than 35 days).',
    source: 'ESMA FIRDS weekly reference data (gettex, MIC codes MUND and MUNC) and OpenFIGI, refreshed every Saturday. The list date is in the tooltip and on the Health page.',
    status: { kind: 'data' },
    mistakes: 'For a foreign company, the US ADR and the home-market share are different securities: the ADR can be "No" even if the company’s home share is on gettex. Check in the broker app before you trade; the broker can still restrict a stock.',
  },
  exchange: {
    name: 'Exchange',
    what: 'The US stock exchange where the stock is listed.',
    how: 'From the exchange symbol lists.',
    example: '"Nasdaq", "NYSE".',
    read: 'Not good or bad.',
    source: 'Nasdaq Trader and SEC lists, refreshed every day.',
    status: { kind: 'data' },
    mistakes: 'The exchange does not tell you anything about quality.',
  },
  sector: {
    name: 'Sector',
    what: 'The broad business area of the company.',
    how: 'The SEC industry code (SIC) of the company, grouped into sectors.',
    example: '"Information Technology", "Health Care".',
    read: 'Not good or bad. Many scores are ranked within the sector.',
    source: SEC,
    status: { kind: 'data' },
    mistakes: 'SIC codes are old and broad: a company can work in more than one area.',
  },
  industry: {
    name: 'Industry',
    what: 'A narrower description of the business.',
    how: 'The SEC SIC description for the company.',
    example: '"Electronic Computers" for Apple.',
    read: 'Not good or bad.',
    source: SEC,
    status: { kind: 'data' },
    mistakes: 'Some companies keep an outdated SIC code.',
  },
  is_adr: {
    name: 'ADR (foreign company)',
    what: 'Yes if this is an American Depositary Receipt: a certificate for shares of a foreign company, traded in the US.',
    how: 'From the security type in the exchange lists.',
    example: '"Yes" for TSM (Taiwan Semiconductor).',
    read: 'Not good or bad. ADRs add currency and foreign-market risk.',
    source: 'Nasdaq Trader symbol files, refreshed every day.',
    status: { kind: 'data' },
    mistakes: 'One ADR can stand for several (or a part of one) home-market shares: compare prices with care.',
  },
  price: {
    name: 'Price',
    what: 'The last closing price in US dollars.',
    how: 'The official close of the last trading day, adjusted for stock splits.',
    example: '"$336.64".',
    read: 'Not good or bad on its own. Signals need a price of at least $5.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'A low price does not mean "cheap". What matters is the price compared with earnings and value.',
  },
  last_date: {
    name: 'Data as of',
    what: 'The date of the last price used for this stock.',
    how: 'The most recent trading day with a price.',
    example: '"Oct 12, 2026".',
    read: 'It should be the last trading day. An older date means the price is missing.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'A stock with an old date is not eligible for signals.',
  },

  label: {
    name: 'Decision label',
    what: 'The app’s decision for the stock: STRONG BUY — TOP CONVICTION, BUY, WATCH, NO TRADE or SELL / RISK WARNING.',
    how: 'BUY needs every trade rule R1–R12 (fresh data, top 2% rank, four families at 60+, independent agreement, calibrated chance, expected value ≥ +1%, liquidity, no blocking event…). SELL / RISK WARNING comes from exit rules and risk events. Everything else is NO TRADE.',
    example: '"NO TRADE" means the evidence is not strong enough; this is the normal case.',
    read: 'BUY and STRONG BUY are rare. SELL / RISK WARNING means a risk: check the reason on the stock page.',
    source: RULES,
    status: { kind: 'research' },
    mistakes: 'A label is not advice. BUY labels have not passed the validation lab yet. Always read the reasons on the stock page.',
  },
  tier: {
    name: 'Position tier',
    what: 'The suggested position size for a BUY label.',
    how: 'Tier 1 (full size) if the chance the trade works (p̂) is at least 60% and N_eff is at least 3; otherwise tier 2 (half size).',
    example: '"2" means half the normal position.',
    read: '1 = stronger evidence than 2. Empty for stocks without a BUY label.',
    source: RULES,
    status: { kind: 'research' },
    mistakes: 'The size also depends on your risk budget (see the stock page plan).',
  },
  eligible: {
    name: 'Eligible for signals',
    what: 'Yes if the stock is liquid enough for the app to give BUY labels.',
    how: 'Price at least $5 AND average traded value at least $10 million per day AND a price on the last trading day.',
    example: '"Yes" for most large companies; "No" for small, rarely traded stocks.',
    read: 'Only eligible stocks can get BUY labels or appear on Picks.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: '"No" does not mean bad: it means too small or too illiquid for the app’s rules.',
  },
  blocked: {
    name: 'Blocked',
    what: 'Yes if an event blocks new entries right now.',
    how: 'Yes if any blocking event is found: earnings in the next 5 trading days, a share offering, a pending merger, a lock-up expiry, a restatement, an auditor change, a going-concern warning, an investigation or a late filing.',
    example: '"Yes" a few days before an earnings report.',
    read: 'Yes = wait. Blocked stocks cannot get new BUY labels and are not on Picks.',
    source: 'SEC filings (8-K items), the earnings calendar and news tags, every weekday.',
    status: { kind: 'data' },
    mistakes: 'A block is temporary: it does not say the stock is bad.',
  },
  block_reason: {
    name: 'Blocking event',
    what: 'The first event that blocks new entries.',
    how: 'The first blocking event found (see "Blocked").',
    example: '"earnings in 3 trading days".',
    read: 'Empty is normal. Hard risks (going-concern, restatement, investigation) are serious.',
    source: 'SEC filings (8-K items), the earnings calendar and news tags, every weekday.',
    status: { kind: 'data' },
    mistakes: 'Only the first event is shown here; the stock page lists all of them.',
  },
  ev: {
    name: 'Expected value of the 60-day trade',
    what: 'The average gain or loss you could expect from the app’s 60-day trade plan, after costs, compared with the S&P 500.',
    how: 'EV = p̂ × average win − (1 − p̂) × average loss − trading costs. Average win and loss come from similar past predictions.',
    example: '"+0.8%" means: on average about 0.8% better than the market per trade, after costs.',
    read: 'BUY needs at least +1.0%. Most stocks are between −2% and +1%.',
    source: MODEL,
    status: { kind: 'research' },
    mistakes: 'An average over many trades. One single trade can lose much more.',
  },
  p_hat: {
    name: 'Chance the trade works (p̂)',
    what: 'The chance that the app’s 60-day trade plan ends ahead of the S&P 500, after costs.',
    how: 'A model trained on past trades with take-profit, exit and time rules (the "triple barrier"), then calibrated on out-of-sample predictions.',
    example: '"56%" means: in the past, about 56 of 100 similar trades ended ahead of the market.',
    read: 'BUY needs at least 55% (58% in a Caution market) and a 95% lower bound of at least 52%. Most stocks are between 40% and 55%.',
    source: MODEL,
    status: { kind: 'research' },
    mistakes: 'This is for the 60-day trade plan with its exit rules, not for simply holding the stock.',
  },
  gain_per_month: {
    name: 'Expected gain per month',
    what: 'The middle 6-month forecast spread evenly over 6 months.',
    how: 'Median 6-month forecast ÷ 6.',
    example: '"+0.5%" means the middle forecast is about +3% over 6 months.',
    read: 'Higher is better. Typical values are between −1% and +1% per month.',
    source: MODEL,
    status: { kind: 'research' },
    mistakes: 'Stocks do not rise evenly: the real path goes up and down.',
  },
  speed: {
    name: 'Speed (gain per unit of risk)',
    what: 'How much expected gain per month you get for each unit of monthly price movement.',
    how: 'Expected gain per month ÷ (yearly volatility ÷ √12).',
    example: '"0.15" means 0.15% of expected gain per month for each 1% of typical monthly movement.',
    read: 'Higher is better. Above 0.2 is high; negative means a negative expected gain.',
    source: MODEL,
    status: { kind: 'research' },
    mistakes: 'A high speed from a tiny volatility can still be a small gain in dollars.',
  },

  ...horizonDocs,

  f1: familyDoc('f1', 'Opinion', 'What analysts and rating platforms think, beyond what estimate revisions and momentum already show.', 'Analyst consensus, price-target upside, recent upgrades minus downgrades and recommendation trends, combined after removing the part already explained by revisions and momentum.', ANALYSTS),
  f2: familyDoc('f2', 'Revisions', 'Whether analysts are raising or cutting their earnings estimates.', 'Change in this year’s earnings-per-share estimate over 60 days, and the share of analysts raising minus cutting.', ANALYSTS),
  f3: familyDoc('f3', 'Earnings', 'How the last earnings report surprised.', 'Earnings surprise (reported minus expected, scaled by its usual size) and the stock’s reaction around the report.', 'SEC XBRL filings and the earnings calendar (Finnhub), every weekday.'),
  f4: familyDoc('f4', 'Insiders', 'Whether company insiders (managers, directors) are buying shares with their own money.', 'Dollar value and number of opportunistic open-market purchases in the last 90 days (routine and pre-planned 10b5-1 trades excluded), plus changes by top institutional holders.', INSIDERS),
  f5: familyDoc('f5', 'Trend', 'The stock’s own price momentum, after removing the market and sector moves.', 'Residual momentum (12 months minus the last month, after market and sector), industry momentum and the 50/200-day trend.', PRICES),
  f6: familyDoc('f6', 'Quality', 'How profitable and financially solid the business is.', 'Return on invested capital, gross profit ÷ assets, accruals, free-cash-flow yield and debt ÷ EBITDA, as first reported to the SEC.', 'SEC XBRL financial statements, as first reported. Refreshed every Saturday.'),
  n_eff: {
    name: 'Independent evidence (N_eff)',
    what: 'How many truly independent pieces of evidence are bullish.',
    how: 'Count of families scoring 60 or more, discounted when those families usually move together (correlation between families).',
    example: '"2.6" means about two and a half independent reasons to be positive.',
    read: 'BUY needs at least 2.5. Above 3 is strong. Most stocks are below 1.5.',
    source: FAMILIES_SRC,
    status: { kind: 'research' },
    mistakes: 'Four strong families that always agree count as fewer than four.',
  },
  disagreement: {
    name: 'Disagreement (D)',
    what: 'How much the six evidence families disagree with each other.',
    how: 'Standard deviation of the six family scores (0–100).',
    example: '"12" means the families mostly agree; "30" means they point in different directions.',
    read: 'Lower is better. BUY needs 22 or less; above 25 is high.',
    source: FAMILIES_SRC,
    status: { kind: 'research' },
    mistakes: 'Low disagreement with all scores near 50 means "no signal", not "strong signal".',
  },

  consensus: {
    name: 'Analyst consensus',
    what: 'The average rating of the analysts who follow the stock.',
    how: 'Average of the ratings on a 1–5 scale: 1 = strong buy, 2 = buy, 3 = hold, 4 = sell, 5 = strong sell.',
    example: '"2.2" is between buy and hold, closer to buy.',
    read: 'Lower is more positive. Most stocks are between 1.8 and 2.8: analysts rarely say sell.',
    source: ANALYSTS,
    status: { kind: 'data' },
    mistakes: 'Analysts are often too positive. A buy rating alone predicts little.',
  },
  n_analysts: {
    name: 'Number of analysts',
    what: 'How many analysts give a rating for the stock.',
    how: 'Count of analysts in the consensus.',
    example: '"39" for a very large company.',
    read: 'More analysts make the consensus more reliable. Below 3, treat it with care.',
    source: ANALYSTS,
    status: { kind: 'data' },
    mistakes: 'Many analysts does not mean a better stock, only a well-known one.',
  },
  target_upside: {
    name: 'Analyst target upside',
    what: 'How far the analysts’ average price target is above (or below) today’s price.',
    how: 'Average analyst price target ÷ today’s price − 1.',
    example: '"+25%" means analysts’ average price target is 25% above today’s price.',
    read: 'Higher looks better, but most stocks show +5% to +30%. Very high values often come from a price that just fell.',
    source: ANALYSTS,
    status: { kind: 'data' },
    mistakes: 'Targets are usually too optimistic and slow to update. They are not forecasts by the app.',
  },
  rev60: {
    name: 'Earnings estimate revisions (60 days)',
    what: 'How much analysts changed their estimate of this year’s earnings per share in the last 60 days.',
    how: 'Current estimate ÷ estimate 60 days ago − 1.',
    example: '"+3%" means the earnings estimate was raised by 3%.',
    read: 'Positive is good (estimates going up). Typical values are between −5% and +5%.',
    source: ANALYSTS,
    status: { kind: 'data' },
    mistakes: 'For very small earnings (near zero), percentages can look huge.',
  },

  insider_buy_7d: {
    name: 'Insider buying, last 7 days',
    what: 'The dollar value of shares that insiders bought on the open market, filed in the last 7 days.',
    how: 'Sum of open-market purchases (code P) by officers and directors, filed in the last 7 days. Routine buyers and pre-planned 10b5-1 trades are excluded.',
    example: '"$1.2M" means insiders bought about 1.2 million dollars of shares.',
    read: 'Bigger is a stronger sign, especially by several insiders. Most stocks have none.',
    source: INSIDERS,
    status: { kind: 'data' },
    mistakes: 'Insider selling is ignored on purpose: insiders sell for many reasons (taxes, houses).',
  },
  insider_net_90d: {
    name: 'Insider buying, last 90 days',
    what: 'The dollar value of opportunistic insider purchases in the last 90 days.',
    how: 'Sum of open-market purchases by insiders over 90 days, excluding routine and 10b5-1 plan trades.',
    example: '"$450K" means insiders bought about 450 thousand dollars of shares in 3 months.',
    read: 'Bigger is better. $100K+ by a CEO or CFO is a meaningful sign.',
    source: INSIDERS,
    status: { kind: 'data' },
    mistakes: 'Compare it with the company size: $1M is a lot for a small company, little for a giant.',
  },

  vol_63: {
    name: 'Volatility',
    what: 'How much the price usually moves, as a yearly number.',
    how: 'Standard deviation of daily returns over the last 63 trading days × √252.',
    example: '"30%" means a typical yearly move of about ±30%.',
    read: 'Lower is calmer. Large stable companies: 15–25%. Small or speculative stocks: 50% or more.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Low past volatility can end suddenly (news, earnings).',
  },
  atr_pct: {
    name: 'Typical daily range (ATR)',
    what: 'How much the price typically moves in one day, as a share of the price.',
    how: 'Average true range over 14 days (high − low, including gaps) ÷ price.',
    example: '"2.0%" means a typical daily range of about 2% of the price.',
    read: 'Lower is calmer. The position plan sets its exit level with it.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'It is a typical day, not the biggest possible move.',
  },
  short_pct_float: {
    name: 'Short interest',
    what: 'The share of tradable shares that investors have sold short (bets that the price falls).',
    how: 'Shares sold short ÷ shares available for trading (the float).',
    example: '"8%" means 8 of every 100 tradable shares are sold short.',
    read: 'Below 5% is normal. Above 15% is high: many investors expect a fall, and prices can swing sharply.',
    source: FINRA,
    status: { kind: 'data' },
    mistakes: 'High short interest is a warning, not a buy signal ("short squeezes" are rare).',
  },
  days_to_cover: {
    name: 'Days to cover',
    what: 'How many days of normal trading it would take short sellers to buy back their shares.',
    how: 'Shares sold short ÷ average daily trading volume.',
    example: '"4.5" means 4.5 days of normal volume.',
    read: 'Below 3 is normal. Above 7 is high and can mean sharp moves.',
    source: FINRA,
    status: { kind: 'data' },
    mistakes: 'It changes with volume: a quiet week makes it look higher.',
  },
  iv_30d: {
    name: 'Implied volatility',
    what: 'How much the options market expects the price to move, as a yearly number.',
    how: 'The volatility that makes option prices fit a pricing model, for options about 30 days out, from at-the-money calls and puts.',
    example: '"40%" means the options market expects bigger moves than a stock with 25%.',
    read: 'Higher means the market expects big moves (often before earnings or news). Compare it with the past volatility.',
    source: 'Yahoo Finance options chains for candidates, every weekday.',
    status: { kind: 'data' },
    mistakes: 'Only shown for candidates with options data; "—" does not mean low.',
  },
  cluster: {
    name: 'Correlation group',
    what: 'Stocks that moved very closely together in the last 6 months get the same group number.',
    how: 'Daily returns over 126 days; pairs with a correlation above 0.7 end up in the same group (hierarchical clustering). Stocks without a close partner have no group.',
    example: 'Two regional banks with the group "12" behave almost like one stock.',
    read: 'Not good or bad. Owning several stocks of one group is less diversified than it looks.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'The number itself means nothing; only "same number" matters. Numbers change every day.',
  },

  change_1d: {
    name: 'Return, last day',
    what: 'The price change on the last trading day, with dividends.',
    how: 'Total return from the previous close to the last close.',
    example: '"−1.1%" means the stock lost 1.1% on the last day.',
    read: 'Not a signal on its own: daily moves are mostly noise.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Do not trade on one day’s move.',
  },
  ret_1w: {
    name: 'Return, 1 week',
    what: 'The total return over the last 5 trading days.',
    how: 'Total return (price change plus dividends) over 5 trading days.',
    example: '"+0.9%".',
    read: 'Not a signal on its own.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Past returns do not predict short-term returns well.',
  },
  ret_1m: {
    name: 'Return, 1 month',
    what: 'The total return over the last 21 trading days.',
    how: 'Total return over 21 trading days.',
    example: '"+3.1%".',
    read: 'Not a signal on its own. Very strong months often partly reverse.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'The last month is excluded from momentum on purpose (short-term reversal).',
  },
  ret_3m: {
    name: 'Return, 3 months',
    what: 'The total return over the last 63 trading days.',
    how: 'Total return over 63 trading days.',
    example: '"+6.2%".',
    read: 'Part of the trend picture.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Compare with the market: +6% is weak if the S&P 500 made +10%.',
  },
  ret_ytd: {
    name: 'Return, this year',
    what: 'The total return since the last close of the previous year.',
    how: 'Total return from the previous year-end close to the last close.',
    example: '"+24%".',
    read: 'Not a signal on its own.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Early in the year it covers only a few weeks.',
  },
  ret_1y: {
    name: 'Return, 1 year',
    what: 'The total return over the last 252 trading days (about one year).',
    how: 'Total return over 252 trading days.',
    example: '"+31%".',
    read: 'Strong 12-month winners tend to keep winning for a while (momentum), but not always.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'A big past gain can also mean the stock is now expensive.',
  },
  trend_up: {
    name: 'Uptrend',
    what: 'Yes if the price is in a classic uptrend.',
    how: 'Yes if price > 50-day average AND 50-day average > 200-day average.',
    example: '"Yes" for a stock rising steadily for months.',
    read: 'Yes is positive for the trend family (F5).',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Trends can end suddenly; "Yes" says nothing about the next week.',
  },
  dist_52w_high: {
    name: 'Distance from 52-week high',
    what: 'How far the price is below its highest close of the last 52 weeks.',
    how: 'Last close ÷ highest close of the last 252 trading days − 1.',
    example: '"−8%" means the price is 8% below its 1-year high.',
    read: '0% is at the high. Near the high often goes with strength; −50% or worse often with trouble.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'A big fall does not make a stock cheap by itself.',
  },

  market_cap: {
    name: 'Market capitalisation',
    what: 'The total stock market value of the company.',
    how: 'Shares outstanding (from SEC filings) × price.',
    example: '"$4.9T" is 4.9 trillion dollars (very large); "$800M" is 800 million (small).',
    read: 'Not good or bad. Large companies are usually calmer; small ones riskier.',
    source: `${SEC} Price: ${PRICES}`,
    status: { kind: 'data' },
    mistakes: 'Share counts update only with filings, so recent buybacks or offerings may be missing.',
  },
  adv_dollar: {
    name: 'Average dollar volume per day',
    what: 'How much money is traded in the stock on an average day.',
    how: 'Average of (close × volume) over the last 21 trading days.',
    example: '"$12.9B" means about 12.9 billion dollars traded per day.',
    read: 'Higher means easier to buy and sell. Signals need at least $10M per day.',
    source: PRICES,
    status: { kind: 'data' },
    mistakes: 'Low volume means wide spreads: your real buying price can be worse than the last price.',
  },

  next_earnings: {
    name: 'Next earnings date',
    what: 'The next expected date of the quarterly earnings report.',
    how: 'From the earnings calendar; companies sometimes change the date.',
    example: '"Nov 2, 2026".',
    read: 'Prices can jump either way at earnings. New entries are blocked in the 5 trading days before.',
    source: 'Finnhub and Yahoo Finance earnings calendars, every weekday.',
    status: { kind: 'data' },
    mistakes: 'An estimated date can move. "—" means no date is known.',
  },
  days_to_earnings: {
    name: 'Days to earnings',
    what: 'Trading days until the next earnings report.',
    how: 'Number of trading days from today to the next earnings date.',
    example: '"3" means the report is in 3 trading days.',
    read: '0–5 blocks new entries. More than 20 days means no report soon.',
    source: 'Finnhub and Yahoo Finance earnings calendars, every weekday.',
    status: { kind: 'data' },
    mistakes: 'Counts trading days, not calendar days.',
  },
}

/** Plain text of a column's validation status (7th part), from health.json's validated list. */
export function statusText(doc: ColumnDoc, validated: string[]): { text: string; validated: boolean | null } {
  const s = doc.status
  switch (s.kind) {
    case 'data':
      return { text: `${NOT_FORECAST} Validation does not apply.`, validated: null }
    case 'research':
      return { text: 'RESEARCH MODE: comes from the app’s models or rules, which have not passed the validation lab yet.', validated: false }
    case 'horizon': {
      const ok = validated.includes(`P(${s.promise}) ${s.h}`)
      return ok
        ? { text: `Validated: this probability passed the holdout test (2024–2026): better than the base rate and well calibrated.`, validated: true }
        : { text: 'RESEARCH MODE: this probability has not passed the holdout test yet.', validated: false }
    }
    case 'record': {
      const ok = validated.includes(`P(up) ${s.h}`)
      return {
        text: `This is the app’s past record, measured on 2016–2023 out-of-sample predictions. ${ok ? '✓ The chance up for this horizon also passed the holdout test (2024–2026).' : 'The chance up for this horizon has not passed the holdout test: RESEARCH MODE.'}`,
        validated: ok,
      }
    }
  }
}
