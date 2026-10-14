# Methodology

How ConvergeAlpha turns free data into labels, probabilities and position plans. Every formula
below is implemented in `pipeline/src/convergealpha/` and covered by tests in `pipeline/tests/`.
The build prompt is the reference; where this document had to choose (the spec left a detail
open) the choice is marked **Choice**.

**Honesty principle.** No tool can make a stock rise for sure. The app puts the odds in your
favour, shows exactly what each percentage promises, and says NO TRADE when the evidence is weak.
Every probability carries a "RESEARCH MODE — not yet validated" badge until the validation lab
passes for that horizon or label.

---

## 1. Data timing (point-in-time)

- Decision time for day D: **16:15 New York**. A daily bar dated D is stored only if it was
  downloaded after D's decision time (`util/calendar.last_completed_session`).
- SEC data counts from its **filing date**, FINRA short interest from an estimated **publication
  date** (settlement + 8 trading days), analyst data from the **snapshot time**, insider trades
  from the **filing date**. Fundamentals keep only the **first-reported** value of each period
  (no restatements) — `sources/fundamentals.first_reported`.
- Prices are stored append-only with the download day (`basis`). Yahoo's prices are
  split-adjusted as of that day, so a later split is applied at load time to rows downloaded
  before it (`sources/prices.adjustment_factors`); the total-return index is rebuilt from closes
  and dividends: r_t = (close_t + dividend_t) / close_(t−1) − 1.
- Leakage tests (`tests/test_leakage.py`, `tests/test_prices.py`) fail the build if a model input
  shares a name with an outcome column, if an unfinished bar could be stored, or if the holdout
  log shows more than one evaluation.

## 2. Universe

US common stocks listed on NYSE, Nasdaq and NYSE American (Nasdaq Trader directories, ETF and
test issues removed; warrants, units, rights, preferreds, notes, funds and blank-check shells
removed by security name; SIC 6770 shells have no sector). ADRs are kept and flagged. Every
ticker ever seen stays in the history. **Eligible for signals** = price ≥ $5, average daily
traded value (21 days) ≥ $10M, priced on the last session.

## 3. Normalization

For each raw signal across the universe on a date: winsorize at the 1st/99th percentile; robust
z inside the sector z = (x − median_sector) / (1.4826 · MAD_sector), clipped to [−3, 3];
score = 100 · Φ(z). A family score is the average of its signal scores, re-normalized the same
way. **Choice:** a sector with fewer than 5 values uses the universe median/MAD; for sparse
signals (MAD = 0, e.g. insider buying is zero for most stocks) the standard deviation is used;
missing values stay missing.

## 4. Evidence families (live)

| Family | Inputs and formula | Notes |
|---|---|---|
| **F1 Opinion** | Platforms: Yahoo consensus (5 − mean)/4·100, Yahoo and Finnhub recommendation trends (2SB + B − S − 2SS)/total, mean-target upside, net upgrades + price-target changes over 90 days, manual CSV ratings. Credibility c = max(h − 0.47, 0.01) with h = (wins + 10)/(signals + 20); F1 = F1_raw − (a + b2·F2 + b5·F5) fitted across stocks, then normalized | No measured credibility yet → equal weights (h = 0.5) |
| **F2 Revisions** | 0.6·z(Rev60) + 0.4·z(Breadth) (+0.2·z(next-year Rev60)), Rev60 = (EPS_FY1 now − 60 days ago)/abs(60 days ago) | **Choice:** breadth uses Yahoo's 30-day up/down counts (60-day counts are not available free) |
| **F3 Earnings** | 0.5·z(SUE) + 0.2·z(news tone), only 1–70 trading days after the report; SUE = (actual − consensus)/stdev of the previous 8 surprises | Revenue surprise has no free source (weight renormalized) |
| **F4 Insiders & ownership** | 0.7·z(insider value) + 0.3·z(institutional accumulation); insider value = log(1 + $bought/100,000) × 1.5 if ≥ 2 insiders bought within 30 days − 0.25·log(1 + $sold/100,000), opportunistic open-market trades filed in the last 90 days | Routine = traded in the same calendar month in each of the 3 prior years; 10b5-1 plan trades excluded |
| **F5 Price & trend** | 0.5·z(residual momentum) + 0.25·z(industry momentum, 6 months) + 0.25·z(trend flag); residual momentum = Σ residuals of months t−12…t−2 / stdev, from a 36-month regression on market and sector returns; capped at 60 if the 1-month return is in the top 5% | Needs ≥ 1 year of history |
| **F6 Quality & value** | mean of z(ROIC), z(gross profit/assets), −z(accruals), z(FCF yield), −z(debt/EBITDA), trailing 12 months from first-reported XBRL facts | Quarters derived from cumulative YTD facts; Q4 = year − 9 months; debt with negative EBITDA = 20 |
| **F7 Context** | Regime, blocking events, liquidity, short interest, implied volatility, news tags | Never votes; blocks or shrinks |

**Independence and agreement.** N_eff = (Σw)² / ΣΣ wᵢwⱼρᵢⱼ over bullish families (score > 50)
(reference tests: 6 at ρ 0.6 → 1.5; 4 at ρ 0.2 → 2.5). **Choice:** until 3 years of live
family history exist, ρ is the cross-sectional correlation of family scores across eligible
stocks. Disagreement D = standard deviation of the available family scores.

## 5. Regime and blocking events

Normal = S&P 500 above its 200-day average and VIX < 25 (and the high-yield spread not up more
than 1 point in 3 months); Stress = below the 200-day average and VIX ≥ 30 (no new buys);
Caution = anything else. Blocking events: earnings within 5 trading days (except entries 1–10
days after a report); share offering (424B1/4/5/7, S-1, F-1 in 14 days, or news); merger/takeover
(SC 14D9, SC TO-T, merger proxies in 90 days, or news); IPO lock-up expiry (≈180 days after the
first price); auditor change (8-K 4.01); restatement (8-K 4.02); SEC/DOJ investigation, going
concern (news keywords); late filing (NT 10-K/10-Q). **Choice:** no free FDA calendar exists, so
FDA dates are shown as news tags only; the AI event layer runs only with an Anthropic key.

## 6. Models (weekly)

Training panel: every month-end since December 2012, eligible stocks only (≈ 2,000–2,500 per
month). Point-in-time features: past returns (1, 3, 6, 12−1 months), residual and industry
momentum, trend, volatility, ATR %, distance from the 52-week high, beta, size, liquidity,
insider value, the five F6 ratios, a seasonal-random-walk earnings surprise from first-reported
XBRL EPS, short interest (2019+), the historical family scores F3h–F6h, their disagreement and
the regime. **F1 and F2 have no point-in-time history before live snapshots began, so they are
not model inputs yet** (spec: zero weight until proven; displayed as information).

Labels: **triple barrier** — entry at the next session's open E, upper E + 3·ATR(14), lower
E − 2·ATR(14), 60 trading days; a gap through a barrier exits at the open; if both barriers are
touched the same day the loss is assumed; "correct" = exit return − S&P 500 return over the same
days − 0.2% costs > 0. Forward returns and excess returns at 5, 21, 63 and 126 trading days.

- **L1**: ridge on the family scores + LightGBM on all features (monotone constraints where
  theory is clear), each ranked within the month and averaged; target = 63-day excess return
  rank.
- **p̂**: LightGBM classifier of the triple-barrier outcome, **isotonic-calibrated per regime on
  walk-forward predictions only**. The isotonic fit uses quantile bins of at least 200 held-out
  predictions, so no probability rests on a handful of extreme cases (plain isotonic regression
  turned a few extreme scores into 0% or 100%). Calibration buckets give the 95% Wilson interval (reference
  test: 230/400 → 57.5%, 52.6%–62.3%) and the bucket's average win W̄ and loss L̄.
- **Horizon forecasts**: calibrated classifiers for "up" and "beat the S&P 500" at 1w/1m/3m/6m;
  LightGBM quantile models (10/25/50/90%) widened by **split-conformal** amounts so the 80% range
  covers 80% of held-out outcomes.
- **L2 meta-model**: logistic regression trained only on L1's top 5% (walk-forward), predicting
  whether that specific trade works, from L1 rank, D, number of families, regime, ATR %, days
  since the report, liquidity, crowding (short interest), distance from the 52-week high, sector.
- **Analogs**: the 200 most similar past setups (standardized features, at most one per stock per
  6 months, never the stock itself); their 6-month up rate with a Wilson interval; a warning when
  model and analogs differ by more than 8 points. Top Conviction rule C7 needs ≥ 100 such setups
  with a Wilson lower bound ≥ 65%.
- Walk-forward: yearly refit; each model trains only on rows whose label window plus a 10-day
  embargo ends before the test year (purge = label horizon + 10 trading days).

Costs: C = spread + 2·commission + 2·impact, impact = 0.5·σ_daily·√(order/ADV) (reference test
0.29%). Spread estimated from liquidity (0.03%–0.3%), commission 0.02% per side, order $10,000
(your own size is used in the browser). EV = p̂·W̄ − (1 − p̂)·L̄ − C.

**Fallback before models exist:** P(up) = Φ(((μ − σ²/2)·T)/(σ·√T)) with μ = risk-free +
β·5% + a small alpha (≤ ±4%/yr from the composite family score) and σ = blend of realized and
implied volatility; P(beat) from the alpha and tracking volatility; EV = expected 63-day excess −
costs. Labelled "estimate — not calibrated"; labels built on it are marked provisional.

Speed = expected gain per month (median 6-month forecast ÷ 6) ÷ monthly volatility.

## 7. Labels

BUY needs all of R1–R12: ≥ 5 of 6 families fresh; regime not Stress; L1 rank in the top 2%; ≥ 4
families ≥ 60 and none ≤ 25; N_eff ≥ 2.5; D ≤ 22; p̂ ≥ 55% and its Wilson lower bound ≥ 52% (+3
points in Caution); meta-model ≥ 55%; EV ≥ +1%; no blocking event; price ≥ $5, ADV ≥ $10M,
order ≤ 1% of ADV; portfolio limits (checked in your browser). Tier 1 = p̂ ≥ 60% and N_eff ≥ 3
(full size), else tier 2 (half). WATCH = misses exactly one of R4–R9 by a small margin
(R4: 3 families ≥ 60 or one ≤ 25; R5 ≥ 2.2; R6 ≤ 25; R7 within 2 points; R8 ≥ 53%; R9 ≥ 0.5%).
STRONG BUY — TOP CONVICTION = tier 1 + all families ≥ 60 with ≥ 5 at 70+, N_eff ≥ 3 and D ≤ 15,
≥ 3 opinion sources at their top rating, opportunistic insider buying (90 days) or top-10%
revisions, Normal regime with volatility ≤ 30% and no blocking event, and the analog rule.
SELL / RISK WARNING (screener) = a hard risk event or 4+ families below 35 in a downtrend.
Holdings (browser): HOLD, ROTATE (21+ trading days below the 1-month 25th-percentile forecast
while a candidate is ≥ 1.5× faster), SELL / RISK WARNING (planned exit hit, risk event,
evidence decay = 3 of 6 families < 50, missing data, or the 60-day time stop).

## 8. Position plan

Planned exit X = max(E − 2·ATR, 0.92·E) — always "planned exit level", never "maximum loss".
Gap stress G = E·|mean of the worst 2% overnight returns over 500 days|; risk per share
r = max(E − X, G). Shares = 0.75% · equity · tier / r, capped by ¼-Kelly on the Wilson lower bound
(f* = p − (1 − p)/b; reference: p 0.53, b 11/7 → 23.1%; equity $10,000, E $100, X $92, G $9 →
5 shares), 10% of equity and 1% of ADV. Portfolio limits: ≤ 10 positions, ≤ 25% per sector,
≤ 20% per correlation cluster (average-linkage clusters of stocks with ρ > 0.7 over 6 months),
open risk ≤ 6%, ≤ 3 new buys a day, drawdown throttle (−10% → half risk, −15% → no new buys).
Exits: planned exit; break-even after +1.5 ATR; sell a third at E + 3 ATR then trail at the
highest close − 3 ATR; evidence decay; 60-day time stop unless still a candidate. Entry: the next
session after the first 15 minutes, limit ≤ +1% above the signal close, skip on a > 3% gap up.

## 9. Event patterns

Events: earnings vs the same quarter last year (XBRL SUE buckets), earnings vs consensus (Yahoo
history), opportunistic insider clusters, dividend raises/cuts ≥ 10%, gaps ≥ 5% on ≥ 2× volume.
Returns run from the first tradable open after the event (5 and 21 trading days) minus the
stock's own average for that window in the same calendar years. Luck test: ≥ 20 events for the
stock (or ≥ 200 across its 3-digit SIC peers), Benjamini–Hochberg FDR ≤ 10% across every test
run, the same sign in both halves of history and in the 2024+ holdout. Guidance, buybacks, index
inclusion and 8-K item history have no free dated history and are not tested.

## 10. Validation lab

Development = walk-forward 2016–2020, validation = 2021–2023, holdout = 2024 to mid-2026,
**evaluated once per configuration** (logged with a hash in the private data repo; a second
evaluation is flagged as contaminated and fails the check). Strategy: top 2% by L1, monthly,
equal weight, 21-day excess return vs the S&P 500 net of turnover × 0.2%. Reported: net excess vs
the S&P 500 and every baseline (momentum only, equal-weight family average, all eligible),
hit rate with payoff and EV (60-day triple-barrier trades), Brier score vs base rate, calibration
slope, max drawdown, turnover, by regime/sector/size, 2× costs, deflated Sharpe ratio (trials =
all variants tried), probability of backtest overfitting (CSCV), and ablation (one family at a
time; kept only if removing it costs ≥ 0.5%/yr in both development and validation). Pass:
net excess > 0 with t ≥ 2 in all three periods, ≥ +1%/yr over the best baseline (after the
haircut), holdout ≥ 50% of development, calibration slope 0.8–1.2, max drawdown < 25%,
DSR ≥ 0.95, PBO ≤ 20%. Forecast horizons leave research mode only if their holdout Brier beats
the holdout's own base rate with a calibration slope of 0.8–1.2. The holdout record also lists a
local dry-run evaluation on 2026-10-12 made before the calibration change above, so the site
reports the holdout as evaluated twice. Revisions-only and third-party lists cannot be
backtested (no point-in-time history).

## 11. Ledger and monitoring

Every new BUY, STRONG BUY and SELL / RISK WARNING is appended to `ledger/ledger.jsonl` the day it
appears, with the scores-snapshot path and its SHA-256, the model version, all probabilities and
forecasts, and a SHA-256 hash chained to the previous entry. Outcomes (1w/1m/3m/6m return and
excess vs the S&P 500) are appended later to a separate chained file; past entries are never
edited (`tests/test_ledger.py` includes the tamper test). The scorecard compares predicted with
realized frequencies per label and horizon. Kill switch: live drawdown −15%, rolling 12-month
net excess < −5%, or a data-health failure → no new BUY labels, a banner and (if configured) a
Telegram alert. Drift: population stability index of each model input vs the last two training
years (alert > 0.25).

## 12. "How often was it right?" (reliability per horizon)

Built by the weekly job from the walk-forward out-of-sample predictions of the development and
validation years only (2016–2023; the 2024–2026 holdout is never used). For each horizon (1w, 1m,
3m, 6m) and each promise ("up", "beat the S&P 500"):

1. **Cross-fitted calibration**: the probability of a case from year Y comes from a binned
   isotonic calibration (bins of ≥ 200 predictions, as for p̂) fitted on the other years only,
   so a bucket's hit rate is never measured on the outcomes that shaped its own calibration.
2. **Buckets**: the same fixed edges as the p̂ buckets (0.35, 0.40, 0.45, 0.48, 0.50, 0.52,
   0.55, 0.58, 0.62, 0.66), extended with 0.20, 0.25, 0.30, 0.70, 0.75 and 0.80 because horizon
   probabilities spread wider. A bucket with fewer than **200 cases** is merged with the next one
   (the last small one joins the bucket below), so every bucket rests on at least 200 outcomes.
3. Each bucket stores n, the actual hit rate and its **95% Wilson interval**.

The daily build looks up each stock's bucket from its calibrated probability (rounded to 4 decimals,
exactly as exported, so the site finds the same bucket) and exports the hit rate, Wilson low/high
and n (`hit_up_<h>` in the screener; up and beat on the stock pages and in `picks.json`). Only model
forecasts get a record; the fallback estimate has none.

Caveat shown on the site: cases overlap in time (monthly rows, multi-month horizons) and stocks
move together, so the true uncertainty is wider than the Wilson range. A ✓ means the horizon's
probability also passed the holdout test (section 10).

## 13. Picks (fixed weights, research mode)

All weights below were fixed before any result was looked at and are never fitted to past data
(`pipeline/src/convergealpha/decide/picks.py`; a test pins them).

- **Universe**: eligible stocks, without a SELL / RISK WARNING label, without a blocking event,
  with a complete 6-month forecast (P(up), median, 10th and 90th percentile).
- **Components** are sector-neutral percentile ranks among those candidates:
  (rank − 1) ÷ (n − 1) × 100, so 0 = weakest and 100 = strongest in the sector. Sectors with fewer
  than 10 candidates are ranked against all candidates. A sub-score is the weighted average of its
  components (weights of a missing component are spread over the others), ranked again the same way.

| Sub-score | Components and weights |
|---|---|
| Confidence | 0.70 × chance of rising + 0.30 × how often the app was right for that chance (Wilson lower bound of its reliability bucket). The chance is the validated P(up) 6m; if 6m is not validated, the validated P(up) 1m; if neither, p̂ with its own bucket's Wilson lower bound. |
| Upside | 0.75 × median 6-month forecast + 0.25 × 90th-percentile 6-month outcome |
| Safety | 0.35 × low volatility (63-day) + 0.35 × smaller downside (10th-percentile 6-month outcome) + 0.20 × quality family F6 (missing = 50) + 0.10 × no earnings report in the next 5 trading days (known date not within 5 days = 100, unknown date = 50, within 5 days = 0) |

- **Balanced** = (Confidence + Upside + Safety) ÷ 3. A stock is a pick only if **each** of the
  three is at least **40**, so a pick is never strong in one area and terrible in another. The
  floor applies to every tab.
- Tabs (top 25 each): Balanced, Safest (by Safety), Most upside (by Upside), Most likely to rise
  (by Confidence); ties broken by Balanced. With the finanzen.net zero box ticked, the page shows
  the top 25 among stocks not known to be unavailable there (`tabs_zero`).
- Each pick lists 2–3 reasons (families scoring ≥ 55, strongest first; if fewer than two, the
  best sub-score) and one main risk chosen by fixed priority: earnings within 5 days, short
  interest ≥ 15% of float, a family ≤ 25, volatility ≥ 50%/yr, else the 10th-percentile 6-month loss.
- **Live tracking only**: the scores snapshot stores each stock's `pick_rank`; the live baseline
  race adds "Picks – Balanced top 25": each month's first snapshot that has picks, the 25 balanced
  picks equally weighted, held 21 trading days, excess return vs SPY after a 0.2% round-trip cost —
  the same rules as the other live strategies. There is **no backtest**: the strategy uses the
  model's current forecasts, and the 2024–2026 holdout must not be evaluated again. The page keeps
  its RESEARCH MODE badge until the strategy is proven live.

## 14. finanzen.net zero availability

finanzen.net zero routes every order to **gettex** (Börse München's market-maker segments, MIC
codes MUND and MUNC). The weekly job downloads the newest **ESMA FIRDS** full equity files (the EU's
official reference data: every instrument each EU venue trades, as reported by the venue), keeps
the gettex shares and depositary receipts (CFI codes ES and ED) that are not terminated, and maps
each ISIN to a US ticker with the **OpenFIGI** mapping API (exchange code "US"; results cached in
the data repo, new ISINs looked up weekly, old ones re-checked after 28 days). gettex lists ≈ 8,600
such instruments, in line with the broker's own "more than 8,500 shares".

Per stock: **true** if its exact US-listed security is on the list; **false** if it is not;
**unknown** if there is no list, the list is older than 35 days, or the stock has traded in the
US for less than 30 days (the weekly file may not have it yet). Unknown is never treated as "not
buyable": with the tick box on, unknown stocks stay visible, marked "?". A foreign company's US ADR
is a different security from its home-market share, so an ADR can be "No" even when the home share
is on gettex. A hand-made list `manual/brokers/finanzen_zero.csv` (column `isin` or `ticker`)
replaces the FIRDS list when present. Source credit: ESMA FIRDS; reuse is authorised with the
source acknowledged (transformation: filtered to gettex shares, mapped to tickers).

## 15. Trading costs in euros (shared by Plan, strategies and "Give me a strategy")

`pipeline/src/convergealpha/decide/costs.py`, mirrored in `web/src/lib/costs.ts`; both are tested
with the same reference values.

- **Fee per order**: 1.00 € per buy and 1.00 € per sell by default (finanzen.net zero; the Plan page
  lets you change it — check the broker's current price list). Version 1 of the paper strategies
  uses 1 € each way; version 2 uses the finanzen.net zero rule (0 € from 500 €, 1 € below).
- **Spread**: the existing liquidity estimate (`decide/rules.spread_estimate`: 0.03% at ≥ $200M a
  day, 0.06% at ≥ $50M, 0.12% at ≥ $10M, 0.3% below, 0.5% unknown). Half is paid on the way in,
  half on the way out. Market impact is left out (a 200 € order is a tiny share of a liquid stock's
  volume). **Choice:** gettex market makers can quote wider spreads than US exchanges, especially
  outside US hours; the estimate is the US-market one.
- **Currency**: price in euros = US price ÷ DEXUSEU (FRED, US dollars per euro), using the latest
  rate dated on or before the day. FRED publishes DEXUSEU about once a week, so the rate can be
  up to ~10 days old; every fill records the rate and its date. Plan results assume the rate stays
  the same; the strategies' values move with it.
- **Whole shares** by default: shares = ⌊(amount − buy fee) ÷ (euro price × (1 + spread/2))⌋;
  money left over stays as cash. Fractional shares are a setting labelled "simulation only".
- **Break-even move** = (money spent + sell fee) ÷ (shares × euro price × (1 − spread/2)) − 1.
  Reference: 100 € with 1 € fees and no spread → 99 € of stock, break-even +2.02% (101/99 − 1).
- **Result** in euros for a stock move m = shares × euro price × (1 + m) × (1 − spread/2) − sell fee
  − money spent. Round-trip cost of a position worth V = (buy fee + sell fee)/V + spread; cost of
  switching one position for another = (sell fee + buy fee)/V + spread_out/2 + spread_in/2.
- Dividends (strategies only): credited to cash on the ex-date at 85% (15% US withholding tax with
  a W-8BEN form). German taxes: section 19 (your own results); the paper strategies show results before tax.

## 16. Opportunity badge

`pipeline/src/convergealpha/decide/opportunity.py`. One badge per stock that joins the event signals
the app already had (insider-buying lists, earnings, dividends, gaps, estimate changes, analyst
upgrades, news tags) with the event-pattern luck test (section 9), the families, the validated
chance up and the blocking/risk checks. Fixed in advance; nothing was fitted.

**Fresh events** (public in the last 7 calendar days, up to the decision day):

| Event | Definition | Tested pattern ("this kind of event") |
|---|---|---|
| Insider cluster buy | ≥ 2 different insiders with opportunistic open-market buys (code P, not routine, not 10b5-1) filed within 30 days, the latest in the last 7 days | Opportunistic insider buying cluster |
| Insider buy | one insider, same rules | none (only clusters are tested) |
| Earnings beat | reported EPS above the consensus (Yahoo calendar) and a positive first trading day (open → close of the first session after the report); a beat whose reaction is not known yet cannot confirm | Earnings above last year (well above if the consensus SUE ≥ 2): the closest tested earnings pattern |
| EPS up vs last year | a new 10-Q/10-K (XBRL, first reported) with EPS above the same quarter a year earlier | Earnings above / well above last year |
| Dividend raised | ex-date in the last 7 days, ≥ 10% above the previous payment | Dividend raised ≥ 10% |
| Gap up on volume | open ≥ 5% above the previous close on ≥ 2× the 50-day volume, last 5 sessions | Gap up ≥ 5% on heavy volume |
| Estimates raised | this year's EPS estimate up ≥ 1% in 7 days, more analysts raising than cutting | none (no free dated history) |
| Analyst upgrade | an upgrade dated in the last 7 days | none (not tested by the engine) |
| Positive news | a headline tagged guidance raised, buyback, dividend raised or upgrade **whose subject is the company** (its ticker, the first word of its name or its first two words joined appear in the first five words: news feeds attach an article to every company it mentions) | none: **news alone is never green** |

**History** for an event comes from the weekly engine, which now exports every test it ran (n,
share of cases that went up, average return from the next open, average excess over the stock's
own same-year average, q-value, both halves, holdout sign, passed) for each (stock, event, window)
and each (3-digit SIC industry, event, window). The stock's own record is used if it was tested
(≥ 20 events), else its industry's (≥ 200 events); a window that passed is preferred, then 21 days,
then 5 days. The luck test itself is unchanged.

**Colours** (the usual up rate = pooled hit rate of the 2016–2023 reliability buckets for that
horizon, e.g. 1 month ≈ 54%):

- **GREEN "Confirmed opportunity"** only if all hold: (1) a fresh positive non-news event whose
  kind PASSED the luck test with a positive average excess; (2) at least 3 of 6 families ≥ 60;
  (3) the validated chance up (1 month if validated, else 6 months) ≥ its usual rate + 3 points;
  (4) eligible, not blocked and not SELL / RISK WARNING.
- **RED "Hype / be careful"**: a trigger — a jump (≥ +10% in a day or ≥ +20% in a week), a gap up
  on heavy volume, or a positive news headline — together with weak evidence (fewer than 2
  families ≥ 60) or a risk flag: short interest ≥ 15% of float, share offering, going-concern
  warning, restatement, auditor change, SEC/DOJ investigation, late filing, pending merger, a SELL /
  RISK WARNING label, or a passed pattern pointing down (this kind of event was usually followed by
  a worse-than-normal return).
- **AMBER "Possible, not confirmed"**: any other fresh positive event. Risk flags are listed in the
  "Why?" panel and keep it from being green when they block.
- No badge: no fresh event and no jump, or a jump with decent evidence and no known reason.

The "Why?" panel shows each event with its date and source link, what history says (n, how often
it went up, average move, luck-test result), the four green checks, and what is missing or risky.
Shown on Today, Screener (column "Opportunity" + filter + "Opportunities" preset), Picks, Plan,
Strategies and the stock page. **Choice:** intraday alerts stay separate warnings (Today, stock
page); badges change only after the close, like labels.

## 17. Plan builder

`web/src/lib/plan.ts` (in the browser, for your amount) with `plan.json` from
`pipeline/src/convergealpha/decide/plan.py`. Thresholds are pinned by tests on both sides.

- **Candidates**: the Picks candidates (eligible, not SELL / RISK WARNING, not blocked, full
  forecast), with the "only finanzen.net zero" setting (unknown stays, marked "?"). Unless you
  allow it, a stock is left out if its next known earnings date falls inside the period **or no
  date is known** (no report can be promised).
- **Sliders**: Safety s → minimum Picks Safety 10 × (s − 1); Upside u → minimum Upside 10 × (u − 1)
  (1 → 0, 10 → 90).
- **Ranking**: (s × Safety + u × Upside + 5 × Confidence) ÷ (s + u + 5); ties by Confidence, then
  ticker. **Choice:** Confidence counts like a middle slider so an uncertain stock does not lead.
  The top 3 stocks you can afford (one share costs less than the amount) are shown, plus "split the
  amount over the top 2" (half each, each paying its own fees).
- **Period**: calendar days 5–180 → trading days = round(days × 0.7) (30 days = 21). At 5, 21, 63
  or 126 trading days one horizon is used; in between, every number (chance up, median, 10th/90th
  percentile, reliability rate and range) is a straight-line mix of the nearest two, and the page
  says so. Below 5 trading days the 1-week forecast is used.
- **Distribution**: median and the conformal-widened 10th/90th percentiles of the model; the 25th
  and 75th are placed on a bell shape between them (median ∓ (median − p10 or p90 − median) ×
  0.6745/1.2816) — no separate 75th-percentile model exists, and adding one would change the model
  configuration. The cumulative curve is a straight line between the five points, extended past
  the ends, clamped to [0, 1].
- **Chance of ending with more money** = calibrated chance up − (F(break-even) − F(0)): the
  validated probability at 0, lowered by the forecast mass between 0 and the cost hurdle.
- **How often right**: the reliability bucket of the chance up at each horizon used (2016–2023 only),
  rate and 95% Wilson range, mixed when two horizons are used (n = the smaller one).
- **Results**: middle / bad (1 in 10) / good (1 in 10) = result at the median / 10th / 90th
  percentile. For the split: the two stocks are assumed to move together (outcomes at the same
  percentile add up; the chance is found on that combined curve) — the cautious case.
- **Verdict**: GREEN "Good opportunity now" only if chance ≥ 55% AND the low end of how often right
  ≥ 52% AND the middle result is above the costs (expected gain > fees + spread) AND every horizon
  used is validated. AMBER "Possible but weak" if chance ≥ 50% and the middle result is above the
  costs. Otherwise GREY "No good opportunity now: waiting is a valid choice". RESEARCH MODE is
  shown on every number whose horizon is not validated.

## 18. Paper-trading strategies (paper money only)

`pipeline/src/convergealpha/paper/` (rules: `strategies.py`, engine: `engine.py`, page:
`export.py`); tests in `pipeline/tests/test_paper.py`. Nothing connects to a broker.

**Shared rules** (all fixed before the first decision; tests pin every number):

- Start: decision at the close of **Tuesday 13 Oct 2026**, first fills at the open of 14 Oct;
  200 € each; benchmark 200 € into SPY at the first open (one buy fee, a fraction of a share
  because one SPY share costs more than 200 €; SPY itself is not sold to EU retail investors — it is
  only the yardstick), then held.
- Decisions after each close with that day's data only (the build's table and forecasts). Orders
  fill at the next trading day's official open (Yahoo daily open), in euros with half the spread
  and the 1 € fee. Sells fill first; then the buys of the day share the available cash equally.
  Whole shares; leftover money stays as cash. A buy that cannot afford one share at the open is
  cancelled; a sell without an opening price waits for the next open.
- Universe: eligible, not blocked, not SELL / RISK WARNING, with a price and a 1-month forecast.
  New buys need the model forecasts (not the fallback estimate) and an inactive kill switch.
- **Two versions of each strategy** (added 13 Oct 2026, before the first fills): the same rules
  and 200 € each, on (a) **finanzen.net zero stocks only** (= true, "not sure" excluded; keys
  `balanced-v1` …, the versions the owner can copy) and (b) **all stocks** the app covers (keys
  `balanced-all-v1` …, `"universe": "all"` in the hashed parameters). The zero versions' parameter
  hashes stay exactly as recorded at their start (a test pins them). Both started with the close
  of 13 Oct; the all-stocks versions decided from the same day's data in a later run that evening.
- Exit levels use the stock's dollar price against the fill's opening price. Stops (stop-loss,
  trailing stop, a holding turning SELL / RISK WARNING, and for the opportunity hunter a red badge)
  act at once; every other exit (take-profit, score rules, maximum hold) and every switch waits
  for the **minimum hold of 3 trading days** (the fill day counts as day 1). A stock sold is not
  bought again by the same strategy for **5 trading days**.
- **Switch rule**: a holding is replaced only if a candidate's score is at least the strategy's
  margin higher AND its expected 1-month gain (median 1-month forecast) exceeds the holding's by
  more than the switching cost (both fees and both half-spreads, as a share of the position).
- Every action and every kept holding gets a plain-English reason. A day the daily build missed is
  caught up from prices only (fills, stops and limits; no new buys).

| Strategy (key) | Positions | Buys | Score (switch margin) | Exits |
|---|---|---|---|---|
| Best overall (Balanced) `balanced-v1` | 2 | Picks (all three sub-scores ≥ 40), Balanced ≥ 60, validated P(up) 1m ≥ 52%, median 1-month forecast > round-trip cost | Picks Balanced (10) | +8% take-profit, −6% stop, Balanced < 60, SELL label, 63 trading days |
| High risk, high reward `high_risk-v1` | 1 | any stock in the universe with a 1-month forecast | 0.6 × rank of the 1-month 90th percentile + 0.4 × rank of F5 (missing = 50), ranks 0–100 within the universe (10) | −12% stop, trailing stop 10% below the highest close, +20% take-profit, 21 trading days |
| Safest with the most upside `safe_upside-v1` | 2 | Picks Safety ≥ 75 | Picks Upside (10) | −5% stop, +6% take-profit then rotate into the next safe stock, 63 trading days |
| Most likely to rise (Confidence) `confidence-v1` | 2 | validated P(up) 1m ≥ its usual rate, a reliability record | 100 × P(up) 1m × reliability low end 1m (2) | −7% stop, P(up) 1m below its usual rate, 21 trading days |
| Opportunity hunter `opportunity-v1` | 1 | GREEN opportunity badge only; cash otherwise | 100 − 10 × trading days since the confirmed event (10) | −8% stop, +12% take-profit, badge turns red, 15 trading days |

Ties are broken by the Picks Balanced score, then the ticker. **Choice:** the parameters were not
adjusted on 2016–2023 data: these strategies use daily numbers (Picks sub-scores, badges, F1/F2)
that have no point-in-time history, so a fair backtest is impossible, and changing numbers without
one would be guessing. "Usual rate" = the pooled 2016–2023 up rate for 1 month (section 16).

**Versions**: each strategy's parameters are hashed into its `start` entry. If the code's rules
ever differ from that hash under the same version, the engine refuses to trade it and the page
says so: a rule change must be a new version (e.g. `balanced-v2`) with its own start, money and
ledger entries; older versions keep running unchanged and old history stays.

**Version 2** (from the close of **Wednesday 14 Oct 2026**; keys `balanced-v2` …,
`balanced-all-v2` …, `sp500-v2`; hashes pinned by a test). The same five ideas (scores, entry
filters and special exits as in the table above), with what was learned since version 1:

- **5,000 €** each (benchmark: 5,000 € into SPY at the first open). Up to **8 stocks** for
  Balanced, Safe upside and Confidence, **4** for High risk and Opportunity hunter: about 625 € or
  1,250 € per order, so most orders reach finanzen.net zero's free level.
- **Fees: the finanzen.net zero rule** (0 € for an order worth 500 € or more, 1 € below), applied
  to each order's value, buys and sells. No hard minimum order: a good stock is not skipped to save
  1 €.
- **EUR/USD: the European Central Bank's daily reference rate** (version 1 keeps FRED's, its
  recorded rule). A day without an ECB rate on or before it waits, like version 1 without FRED.
- **One tested sell rule for all five**: −5% stop, +6% take-profit, at most 63 trading days, no
  trailing stop. It is the rule chosen by research protocol `rules-2016-2023-v1` (section on sell
  rules, Validation page), fixed before that run and run once on 2016–2023 only. The trade-off is
  shown, not hidden: it cut the average of the worst 5% of trades from about −38% to about −13%
  but also the average trade from about +3.2% to about +0.4%, and about 30% of stopped stocks
  were back above the buy price 21 days later. Version 1 keeps its own exits, so the two are
  compared live: if version 2 does not beat version 1 after costs over months, the rule did not
  help live.
- Entry stays at the next official open (no other way of buying beat it in both halves of
  2016–2023).
- Nothing in version 2 was chosen with 2024–2026 data.

**Trade ledger** `ledger/trades.jsonl` in the private data repo: append-only and hash-chained like
the signal ledger (`start`, `order`, `fill`, `cancel`, `dividend`, `split`, `day` entries; each
`day` entry stores the value, cash, holdings with their peak and days held, the reasons, the
EUR/USD rate and the SHA-256 of that day's scores snapshot). It is verified at every build and
shown on Health; a test edits a past fill and checks that verification fails. A same-day re-run
finds the day recorded and adds nothing; a weekly run never touches it.

**Waiting orders**: the page shows about how many shares and euros each order gets, estimated from
the last close (sells first, then the cash shared equally between the buys, whole shares, half the
spread and the 1 € fee). The fill uses the opening price, so the real numbers differ a little.

**Status at a glance**: "In cash" (no stocks, no order), "Buys / Trades at the open" (orders waiting
for the next open), "Invested" (holds stocks, no order waiting), "Stopped" (rules changed without a
new version).

**Leaderboard**: value (cash + holdings at the last close), % since 200 €, difference to the S&P 500
yardstick in percentage points, fees paid, filled trades, win rate (sells with a profit after fees ÷
sells), worst drop (largest fall of the daily value from an earlier high), cash. The page keeps
RESEARCH MODE until a strategy is ahead of the S&P 500 live after at least 126 trading days.
"Give me a strategy" applies each strategy's buying rules to today's candidates for your own
amount (2-position strategies split it in half), shows costs, the opportunity colour and a
1-month Plan verdict, and marks as best overall the green or amber suggestion with the highest
chance of ending with more money.

## 19. Your money: tax, goal and your own trade journal

Everything here runs in the browser; your journal, rules and tax profile never leave it.

**German tax (2026 rules, `web/src/lib/taxes.ts`, dated sources in the file).** Flat tax 25% plus
5.5% solidarity surcharge (26.375%); with church tax the flat tax is (e − 4q)/(4 + k) (§ 32d EStG;
e = income, q = foreign tax credited, k = 8% or 9%). Saver's allowance 1,000 € a year (2,000 € joint), used first.
Equity ETFs (at least 51% stocks): 30% of gains and payouts are tax free; the yearly advance tax on
funds (Vorabpauschale) uses the Basiszins (2026: 3.20%). US dividends: 15% withheld at source
(W-8BEN), counted toward the German tax. Germany sells first-bought shares first (FIFO), so the app
never lets you "choose" lots. Results are shown before and after tax where you act (Plan's middle
result, sells, the yearly summary, the goal planner). Your bank's yearly tax statement is the
official number.

**Goal planner (`web/src/lib/goal.ts`).** 4,000 possible futures replayed from about 100 years of
monthly US market history (Kenneth R. French Data Library: total market, 1-month T-bill rate,
inflation), drawn in 12-month blocks so crashes and recoveries keep their real shape (seed fixed:
the same plan always shows the same picture). Inputs: money now (minus emergency cash kept aside),
monthly amount, years, the share in stocks (the rest earns the T-bill rate), the fund's yearly cost,
"today's euros" (after inflation) and "be cautious" (stocks earn 2 points a year less than in
history). Outputs: the chance of reaching the goal, the bad / middle / good outcome by year, the
monthly amount needed for an 8-in-10 chance, simpler alternatives and the result after German tax.
It is history replayed, not a forecast; US data in dollars stands in for a world ETF in euros.

**Trade journal and portfolio (`web/src/lib/journal.ts`, `risk.ts`, `portfolio.ts`).** You log
real trades (euros, fee, reason, "I'm wrong if…", the app's view at that moment). Holdings,
average costs and realized results follow German FIFO. Your written rules (investment policy:
goal, horizon, largest loss you accept, stocks, share per stock, trades per month, smallest order,
cooling-off hours, only finanzen.net zero, no earnings within N days) are checked before every
trade; the app warns, it never blocks. Cooling-off: a buy after +10% in a week or a ±7% day, a
sale after −8% in a week, or 2+ trades within the cooling-off period suggests waiting. Risk: a
bad month as the average loss in the worst 1 in 20 months (bell-curve CVaR from each stock's
volatility, correlation 0.7 inside a cluster, 0.5 inside a sector, 0.3 otherwise, 0.8 in a
crash), every stock −20% at once, the biggest holding gapping −20% overnight, sector and cluster
concentration, and a before/after view of a planned trade. Drawdown brake: 10% below the peak =
half-size new positions, 15% = no new buys. Review: trades and fees this month vs your limit,
chasing and panic counts, winners sold earlier than losers, whether ignoring warnings paid off,
and each closed trade scored as good/weak decision × good/bad result. Paper trades (for example a copied
strategy, "practice first") are kept in the same journal with a paper flag and never count as
holdings, warnings, sizing, measured costs or tax. "Copy it with your money" scales a strategy's
holdings to your amount (whole shares, the finanzen.net zero fee rule, a euro limit price per order).

## 20. Research run once (fixed protocols and the experiment log)

A question about the past is answered by a protocol written in code before the run (its settings
hashed into a digest); it may run once (`already_run` refuses a second run; an audit re-run does
not record). Only 2016-2023 is used; the 2024-2026 holdout is never read. Every run, failures
included, is appended to `ledger/experiments.jsonl` (hash-chained, published as experiments.json),
so a lucky result cannot hide behind unreported tries.

- `rules-2016-2023-v1` (sell rules and entry timing, `research/rules.py`): run 14 Oct 2026. Chosen:
  −5% stop / +6% take-profit / 63 days (best score in both halves), entry at the next open. The
  trade-off is published (section 18, version 2).
- `corrections-2016-2023-v1` (sector and stock corrections of the chances of rising,
  `research/corrections.py`): fit on 2016-2020, judged on 2021-2023; adopt only if the test Brier
  improves by 0.2%+ and in 2 of 3 years. Run 14 Oct 2026: **nothing adopted**. Every correction made
  the test years worse (1 week −0.19%, 1 month −0.16%, 3 months −0.34%, 6 months −0.74%); the
  sector biases of 2016-2020 (e.g. Energy) reversed in 2021-2023. The weekly job refits only
  adopted corrections, so none is applied.
- `exam2-2026h2-v1` (the second clean exam, `research/exam2.py`): **registered on 14 Oct 2026, before
  any of its outcomes existed**. Forecasts published 12 Oct - 31 Dec 2026, judged once on or after
  1 Jul 2027: a horizon passes only if its Brier score beats the usual 2016-2023 up rate and stocks
  given 60%+ rose at least 55% of the time with the low end of a 95% Wilson range above 50%
  (non-overlapping forecast days). Pass or fail, the result is logged next to the registration.

## 21. Reliability: checks, records and rollbacks

- **Price checks before use (`quality.py`).** Every eligible stock (and every paper holding) is
  checked each day: impossible values (≤ 0, high below low, close more than 1% outside the day's
  range), a move of more than 50% without a recorded split, the same close for 5 days. Up to 55
  stocks (flagged jumps first, then the strategies' holdings and orders, SPY and yesterday's top
  picks) are compared with Finnhub's free quote: within 2% = confirmed (a confirmed jump is real
  news, not bad data); 2-10% apart = a warning; more than 10% = wrong data. A failing stock is
  blocked for new buys that day ("price data failed a check"); stored prices are never changed.
- **Incident log (`ledger/incidents.py`).** Each build checks: a core source failed, under 90% of
  stocks priced, a price check blocked stocks, ECB vs FRED gap above its limit, a ledger failed
  verification, paper trading did not run normally, the kill switch, the fallback forecasts, a
  model that failed the weekly gate. An incident is opened the first day and resolved the first
  day it passes; quiet days are recorded too. Hash-chained, published in full (incidents.json,
  Health).
- **Safe deploy (`web/scripts/gate.mjs`).** Before the site is published, its data is compared with
  the live site: unparsable files, missing core files, fewer than half the live site's stocks, or
  data older than what is live stop the deploy, so the live site keeps its previous version.
- **Weekly model gate (`models/gate.py`).** A new bundle is used only if, on the same 2016-2023
  walk-forward years, its Brier score is at most 2% worse, its AUC at most 0.01 lower, each 80%
  range holds 70-90% of outcomes, and its training data did not shrink by more than 10%.
  Otherwise the weekly run fails and the daily builds keep downloading the last bundle that passed.
- **Replay any day (`paper/replay.py`).** The table the strategies decide from is stored each day
  with its SHA-256 in every day entry. `python -m convergealpha replay-paper --date YYYY-MM-DD`
  rebuilds the books from the ledger, runs that day again with the stored inputs, prices and the
  recorded EUR/USD rate, and compares every fill, order, value and reason with the ledger (floats
  rounded as the ledger stores them). Possible for days from 15 Oct 2026.
- **Public fingerprints.** Each day `commitment.json` holds the SHA-256 of the forecasts, of the
  strategies' inputs and of this month's forecast archive, and the latest hash of every ledger; the
  daily workflow appends it to the public repository's `ledger-heads` branch, where GitHub records
  the time. A forecast or trade changed later would no longer match.
- Dependabot proposes grouped dependency updates weekly (CI tests each one).

## 22. Learning from its own results

- **Live report card (`ledger/report_card.py`, Scorecard page).** Every eligible stock's chance of
  rising, from every day's first forecast, is compared with its real total return once the
  horizon has passed: how often stocks given 60%+ rose and stocks given 40% or less fell (95%
  Wilson ranges), the Brier score against the usual up rate of 2016-2023, and the share that rose
  per chance bucket. Losers count like winners. Forecasts of consecutive days overlap in time, so
  the ranges are too narrow; the number of forecast days is shown with them. First results: 1 week
  on 19 Oct 2026, 1 month on 10 Nov 2026. The monthly forecast archive is public
  (`data/forecasts/YYYY-MM.json`, chances in thousandths).
- **Live correction (`models/live_calibration.py`).** For each horizon, once at least 4 independent
  periods have matured: gap = log-odds(share that rose) − log-odds(average chance given), weight =
  periods / (periods + 26), shift = weight × gap capped at ±0.5 log-odds, applied to every chance
  of that horizon (the order of stocks never changes). It is fitted on the model's chances before
  the correction (stored as `p_up_raw_*`), so it cannot feed on itself, and only on live forecasts
  (from 12 Oct 2026), never on the holdout.
- **Drift actions.** When 3 or more model inputs drift (PSI above 0.25 against the last two years of
  training data), the position plan sizes new positions at half, and the daily workflow starts the
  weekly retraining early (if the model is more than 3 days old).

- **Signal decay.** For every forecast day, each evidence family's rank correlation with the
  stocks' later 1-week and 1-month returns is measured (eligible stocks). After 6 independent
  periods, a family with a negative average and t below −2 is shown as "not working live": a
  reason for the next rules version, never a silent change.

## 22b. Plain answers on the stock page and your holdings (display only)

`features/explain.py`. None of these feeds a label or a rule until it passes a one-time test.

- **Why did it move today:** today's move = the market (SPY) + the sector beyond the market (median
  move of the sector's eligible stocks − SPY) + its own part (the rest), with that day's headlines
  (Finnhub, for about 150 candidates) and SEC filings; "no public reason found in the news and
  filings the app reads" when there is none. Shown on the stock page, and for moves of 3% or more
  in the screener data and on your holdings.
- **What is already in the price:** the average of two sector percentiles among eligible stocks:
  free-cash-flow yield and earnings yield (last 12 months ÷ market value); 100 = cheapest; 67+
  "cheap for its sector", 33 or less "expensive" (at least 5 stocks per sector).
- **Distress check (simple rules, not a probability):** liabilities above 90% of assets or negative
  equity; cash for less than a year of cash burn; debt above 6× EBITDA or debt with negative
  EBITDA; a late report. 0 flags = low, 1-2 = elevated, 3+ = high; a bankruptcy filing (8-K 1.03),
  a delisting notice (8-K 3.01) or a going-concern doubt is always high.
- **New warnings:** 8-K 1.03 (bankruptcy) and 3.01 (delisting notice) in the last 90 days block new
  buys; 8-K 5.02 (director or officer change, 14 days), 2.06 (impairment, 30 days) and the news tag
  "CEO or CFO leaving" show on your holdings as "check your reason", next to guidance cuts,
  lawsuits, downgrades, investigations, offerings and dividend cuts.
- **Seven questions** on every stock page: why it could rise, how good the evidence is, what could go
  wrong, what is already in the price, what the app does not know, what it would do to your
  portfolio, and whether it beats the simple alternative (a broad ETF).

## 23. Known biases and limits

- **Survivorship bias**: free price history mostly lacks delisted stocks. Every backtested excess
  return is **halved** before it is shown, and the "+1%/yr over the best baseline" check uses the
  halved number.
- **Short opinion history**: analyst snapshots start on 2026-10-12; F1 and F2 enter the models
  only when enough live history exists.
- Yahoo data is unofficial and can change without notice; data-quality checks (split repair,
  impossible, jumping and frozen prices, a Finnhub cross-check; section 21) and the Health page
  show coverage every day.
- IFRS filers have no F6 (only US-GAAP XBRL is parsed).
