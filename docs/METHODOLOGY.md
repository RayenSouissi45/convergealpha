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

## 15. Known biases and limits

- **Survivorship bias**: free price history mostly lacks delisted stocks. Every backtested excess
  return is **halved** before it is shown, and the "+1%/yr over the best baseline" check uses the
  halved number.
- **Short opinion history**: analyst snapshots start on 2026-10-12; F1 and F2 enter the models
  only when enough live history exists.
- Yahoo data is unofficial and can change without notice; data-quality checks (split repair,
  zero/negative prices, stale feeds) and the Health page show coverage every day.
- IFRS filers have no F6 (only US-GAAP XBRL is parsed).
