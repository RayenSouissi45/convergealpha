# Progress

Last updated: 2026-10-13 (end of the Phase 1–7 build run)

- Live site: **https://rayensouissi45.github.io/convergealpha/**
- Code: https://github.com/RayenSouissi45/convergealpha (public)
- Data: https://github.com/RayenSouissi45/convergealpha-data (private: raw data, snapshots, ledger)

| Phase | Deliverable | Status |
|---|---|---|
| 0 Setup | Repos, CI, secrets, deploy | **Done** |
| 1 Universe + prices + screener | 5,356 US common stocks, prices since 2010, screener, stock page | **Done** |
| 2 Evidence data | Analysts, estimates, earnings, insiders, XBRL fundamentals, short interest, options, regime, news | **Done** |
| 3 Families + labels | F1–F7, N_eff, D, R1–R12 / C1–C7, labels, position plan, Today page | **Done** |
| 4 Models + forecasts | L0–L3, 4-horizon forecasts with conformal ranges, analogs, event patterns | **Done** (weekly training on GitHub) |
| 5 Validation lab | /validation: walk-forward, ablation, DSR, PBO, holdout | **Done**. Result: BUY labels **not validated**; some horizon probabilities are |
| 6 Ledger + monitoring | Hash-chained ledger, scorecard, baseline race, kill switch, drift, Telegram | **Done** (Telegram needs your bot, see questions) |
| 7 Polish | PWA (offline, installable), Lighthouse ≥ 90, docs | **Done** (every page ≥ 90 on mobile, see checks) |
| 8 Picks & clarity (2026-10-13) | Picks page, Forecast view, "How often was it right?", finanzen.net zero filter, Columns explained | **Done** (see "Picks and clarity" below) |

## What works

**Every weekday after the close (22:30 UTC, `daily.yml`)**: universe refresh, prices for every stock,
SEC filings and Form 4 insider trades, a rotating share of Yahoo analyst data (plus daily for
~400 candidates, holdings and stocks near earnings), Finnhub trends, calendar and news, options
implied volatility for candidates, FRED macro and FINRA short interest. Then families, regime,
model forecasts, labels and position plans; the ledger records new signals and measures due
outcomes; the site is rebuilt and deployed. 17–40 minutes.

**Every 2 hours in market hours (`intraday.yml`)**: gap, exit-level and drop checks for BUY/WATCH
stocks and your holdings, SEC live filings and negative news. It only warns; labels change after
the close.

**Saturdays (`weekly.yml`)**: XBRL refresh, point-in-time dataset rebuild (≈ 265,000 stock-months
since 2012), walk-forward training, calibration, analog index, event-pattern tests, validation
lab, "how often was it right?" tables. Refreshes the finanzen.net zero list (gettex shares from
ESMA FIRDS, mapped to tickers with OpenFIGI). Publishes the model bundle for the daily builds.

**Website** (phone first): Today, Screener (5,356 rows, virtualized, presets, filters, column
chooser), Stock page (decision card with every rule, forecasts and ranges, families, position
plan, evidence sections, chart, analogs, patterns), Compare, My portfolio (stored in your
browser), Scorecard, Baseline race, Validation, Health, About & method. Missing values show "—"
and explain why. RESEARCH MODE badges stay on until something passes validation.

**Picks and clarity (added 2026-10-13)**:
- **Picks** (`/#/picks`, in the bottom bar and linked from Today): the best-balanced suggestions.
  Safety, Upside and Confidence are sector-neutral percentiles (0–100) with weights fixed in
  advance; a pick needs 40+ on each. Tabs Balanced / Safest / Most upside / Most likely to rise,
  top 25 each. Every card shows the three bars, expected change and chance up for 1W/1M/3M/6M,
  "how often this was right before", 2–3 reasons, the main risk and a link to the stock page.
  Research banner on top; tracked live as "Picks – Balanced top 25" in the Baseline race.
- **Screener Forecast view** (`/#/screener?preset=forecast`): expected change (with the 80%
  range), chance up and how often right (±, ✓ or "research") per horizon; one horizon at a time
  on phones (1W | 1M | 3M | 6M chips), all four on desktop. A one-line legend explains the three numbers.
- **How often was it right?**: per horizon, the hit rate of past forecasts with a similar chance
  (2016–2023 out-of-sample, ≥ 200 cases per group, 95% Wilson range) on the stock page, in the
  screener and on Picks; explained on the About page.
- **Only stocks I can buy on finanzen.net zero**: a tick box on Screener, Picks, Today and
  Compare (remembered in the browser) with a count, a small "✓ buyable" badge, and the list date
  and match count on Health.
- **Columns explained** (`/#/columns`): every column in plain English (meaning, formula,
  example, good/bad, source, validation status, common mistakes); full column names in the
  screener headers (wrapped, never cut off) and in the column chooser.

### Checks run (2026-10-12 and 13)

- GitHub: `ci`, `deploy`, `daily`, `intraday`, `bootstrap`, `backfill` and `weekly` all ran by
  hand and succeeded; CI and deploy are green for every commit. The first scheduled `daily` and
  `intraday` runs also succeeded (GitHub started them late, see Known limits).
- Tests: 84 pipeline tests (all section 13 reference values, leakage, holdout once per
  configuration, ledger tamper test, validation metrics, calibration, same-day merge), 40 web
  unit tests, 30 Playwright checks at phone and desktop size (2 skipped by design). ruff, strict
  mypy, oxlint and TypeScript are clean.
- Lighthouse on the live site, mobile, real data (performance): Today 97, Screener 91–96
  (3 runs), Stock 97, Portfolio 99, Validation 94–96, Health 98. Accessibility 100 on every
  page; best practices 100 on Today, Screener and Stock.
- Live `health.json` after the 2026-10-13 03:21 UTC build: 13 of 15 sources live; prices for
  5,355 of 5,356 stocks; analyst snapshot ≤ 8 days old for 100% (consensus for 53%); EPS
  revisions 74%; XBRL quality ratios 87% of stocks, 93% of eligible ones; options implied
  volatility for 753 candidates; news for 146 stocks; ledger 664 entries, chain verified, no
  stock recorded twice for the same day; kill switch off.

### Validation result (first weekly run)

GitHub weekly run 38309891938, model `m-20261012-7ef7099b4d`, 264,766 stock-months
(2012–2026). Walk-forward AUC of the 60-day trade label: **0.517**, a weak signal. All excess
returns below are halved (survivorship haircut).

| Check | Result | |
|---|---|---|
| Net excess > 0 with t ≥ 2: development / validation / holdout | +1.93% (t 0.79) / −0.70% (t −0.17) / +5.58% (t 1.21) | Fail ×3 |
| ≥ +1%/yr over the best baseline: development / validation / holdout | −10.47% / −0.70% / +5.58% | Fail, Fail, Pass |
| Holdout ≥ 50% of development | +5.58% vs +1.93% | Pass |
| Calibration slope 0.8–1.2 (holdout, trade label) | 0.67 | Fail |
| Max drawdown < 25% | −30.6% | Fail |
| Deflated Sharpe ≥ 0.95 | 0.51 (8 trials) | Fail |
| Probability of backtest overfitting ≤ 20% | 50% | Fail |
| Holdout evaluated only once | 2 evaluations (decision 26) | Fail |

- **BUY labels: not validated** (2 of 12 checks). They keep their RESEARCH MODE badge.
- **Validated probabilities:** chance of being higher in **1 month** and **6 months** (holdout
  Brier score better than the holdout's own base rate, calibration slope 1.06 and 1.03). All
  other probabilities keep a * and the research badge. The 80% ranges hold 76–81% of outcomes.
- **Ablation:** only F4 (insiders) clearly helps in both periods; F3, F5 and F6 help in
  2021–2023 but not in 2016–2020.
- The momentum baseline beat the app in 2016–2020; the app beat every baseline in 2021–2023
  and on the holdout, but not by a statistically meaningful margin.

## Decisions made

Hosting and storage
1. Public code repo + GitHub Pages (your choice): free Actions minutes and hosting; no secrets or raw data in it.
2. Private `convergealpha-data` repo written through a deploy key (`DATA_DEPLOY_KEY`): your instruction; licensed raw data stays private.
3. Hash URLs (`/#/stock/AAPL`) and relative asset paths: the same build works on GitHub Pages and Cloudflare Pages without server rules.
4. `robots.txt` blocks search engines: personal site. Anyone with the URL can still open it (see question 6).
5. Model bundle passed between workflows as an Actions artifact (90 days), not committed: keeps the data repo small.
6. Daily job split into prepare → 6 parallel price/Yahoo shards + Finnhub → build → deploy: fewer Yahoo requests per runner, ≈ 40 minutes.
7. The weekly job re-enables the schedules: GitHub disables them after 60 days without repo activity.

Data
8. Yahoo Finance (yfinance) for prices and analyst data: the only free source covering 5,000+ US stocks with history; personal use; raw data never published.
9. Prices stored as downloaded, with splits applied when loading: storage stays append-only when a split rewrites history.
10. Total return built from close + dividends: Yahoo's adjusted close changes retroactively.
11. Price history from 2010: enough warm-up for the 2016–2020 development period.
12. Yahoo analyst data refreshed for 1/5 of stocks per day, plus daily for ~400 candidates, holdings and stocks near earnings: rate limits.
13. Finnhub for recommendation trends, calendar and news; targets and upgrades from Yahoo: those Finnhub endpoints are premium (HTTP 403).
14. SEC insider data sets (quarterly) + daily Form 4 XML; before 2023, 10b5-1 plans are found from footnotes: the checkbox column only exists since 2023.
15. 424B2/424B3 prospectuses don't count as share offerings: banks file thousands of structured-note prospectuses.
16. XBRL facts kept as first reported: restated numbers would leak the future.
17. FINRA short interest used from settlement + 8 trading days: conservative publication date.
18. Loughran–McDonald word lists kept only in the private repo: their licence is non-commercial research.
19. Opinion (F1) and revisions (F2) are not model features yet: no free point-in-time history before 2026-10-12; they are used in rules and scores.
20. Ticker files that Windows cannot store (e.g. `CON.json`) are saved as `CON_.json`: the build must also work on Windows.

Models and validation
21. Model momentum features are named `mom_*`, with a leakage test: the old names collided with label columns.
22. Walk-forward by year, purge + 10-day embargo; development 2016–2020, validation 2021–2023, holdout 2024-01-01 → 2026-06-30: spec periods; leaves room for 6-month outcomes.
23. Training rows at month-ends only: fewer overlapping labels, manageable compute.
24. Calibration is isotonic on bins of ≥ 200 predictions: plain isotonic turned a handful of extreme scores into 0% or 100%.
25. Each horizon probability can leave RESEARCH MODE on its own (beats the holdout base rate on Brier score, calibration slope 0.8–1.2); BUY labels need all checks: as specified.
26. The holdout is evaluated once per configuration and logged. A local dry run on 2026-10-12 evaluated it once with the earlier calibration, before the change in 24. That evaluation is in the log, so the site says "evaluated 2 times": an honest record over a clean-looking one.
27. Backtested excess returns are halved wherever shown, including the verdict: survivorship bias of free price data.
28. The verdict is recomputed from the stored report at every daily build: rules and wording always match the current code.
29. A failing validation lab doesn't block the weekly model bundle: the models then just stay in research mode.

Website
30. React 19, Vite, Tailwind 4, TanStack Table v8 (not v9): v9 is not stable yet.
31. oxlint instead of ESLint: the official Vite React template moved to it.
32. Core pages load immediately, heavy pages on demand: lazy-loading everything scored worse.
33. `today.json` for the Today page (top 20 per list, ~16 KB compressed): phones no longer download the 0.8 MB screener; the full file loads only if you have holdings or `today.json` is missing.
34. Your portfolio is stored only in your browser; the optional `HOLDINGS` variable gives the pipeline tickers only: the code repo is public.
35. Numbers and dates always use US English: this PC's locale is French.
36. Offline mode: hashed assets cache-first, data network-first: works offline with the last data you opened, never stale when online.
37. No AI news layer: it costs money; Loughran–McDonald + keyword tags are used instead.
38. Telegram is optional and skipped without its secrets; Health shows "not connected".

Re-runs and incidents
39. A second run on the same day merges into that day's files (analyst and options snapshots, news, rating changes, earnings events) instead of replacing them: on 2026-10-12 a second manual run replaced the full analyst snapshot (5,356 → ~1,555 rows) and the day's event files. The bug was found the same evening, fixed (commit a7a2b73) and the lost rows were restored from the data repo's git history (data commit 0ed6297).
40. The first `scores.parquet` of a day is never overwritten; later runs write `scores-HHMMSS.parquet` and their ledger entries hash that file: every ledger entry can always be re-checked against its exact inputs.
41. Ledger entries from that incident are kept, not cleaned up: 364 SELL warnings came from the run with incomplete analyst data, 300 more from the corrected runs (other stocks). The ledger is append-only; deleting entries would defeat its purpose.
42. Each daily build resets `intraday.json` to an empty placeholder, and the Today page shows intraday alerts only from today: no 404 in the console and no stale warnings.

Picks, Forecast view, finanzen.net zero, column explanations (2026-10-13)
43. Picks weights were written into the code and METHODOLOGY before any result was looked at, and a test pins them (Confidence 0.70 chance + 0.30 past hit rate; Upside 0.75 median + 0.25 good case; Safety 0.35 volatility + 0.35 bad case + 0.20 F6 + 0.10 no earnings soon): you asked for no tuning, and fixing them first keeps the live record honest.
44. Sub-scores are percentile ranks within the sector, ranked again after weighting; sectors with fewer than 10 candidates are ranked against all candidates: a rank among three stocks says little.
45. The minimum of 40 on each sub-score applies to every tab, not only Balanced: a pick should never be terrible in one area, whatever the sort.
46. Earnings component: a known date outside the next 5 trading days = 100, an unknown date = 50 (stocks reporting within 5 days are already blocked): an unknown date cannot be called safe.
47. Picks are tracked live only, as "Picks – Balanced top 25" in the baseline race (from the first snapshot that has picks, then each month's first; 21 trading days; equal weight; 0.2% cost): a backtest would need the holdout again.
48. With the finanzen.net zero box ticked, Picks shows the top 25 among stocks not known to be unavailable (precomputed `tabs_zero`) rather than filtering the top 25 down: you still get a full list.
49. "How often right" tables use calibration cross-fitted by year (each year's cases are calibrated on the other years): hit rates measured on the outcomes that fitted the calibration would flatter the model.
50. Their buckets use the p̂ edges extended to 0.20–0.80, merged until each holds at least 200 cases: horizon probabilities spread wider than p̂.
51. Probabilities are exported with 4 decimals and looked up with the same rounded value: the site always finds the bucket the pipeline used.
52. The screener carries only the hit rate per horizon (`hit_up_*`); the bucket tables (range and n) travel once in the file header: 12 more fields per row would have added ≈ 250 KB.
53. The reliability tables sit outside the model configuration, so its digest is unchanged and the weekly job reuses the frozen holdout result instead of evaluating it again.
54. finanzen.net zero list = the gettex shares and ADRs in ESMA's FIRDS register (official, reuse allowed with credit): the broker trades only on gettex, gettex lists ≈ 8,600 of them against the broker's "more than 8,500 shares", and the broker's own site blocks automated access and offers no download.
55. ISINs are mapped to tickers with OpenFIGI (public-domain identifiers) and cached in the data repo; the first full mapping (8,642 ISINs, ≈ 38 minutes without a key) ran once locally: later weekly runs only map new ISINs and re-check old ones.
56. "Buyable" means the exact US-listed security: a foreign company's ADR is a different security from its home-market share.
57. Unknown (no list, list older than 35 days, or a US listing younger than 30 days) is never treated as "not buyable": with the box ticked those stocks stay visible, marked "?".
58. The badge is the app's own small teal "✓ buyable" pill: no broker logo, colours or wordmark.
59. One tick-box setting shared by Screener, Picks, Today and Compare, kept in browser storage (wrapped in try/catch).
60. Screener numbers are rounded per field (returns 3 decimals, family scores 1, probabilities 4): the file gained 17 fields but stayed about the same size.
61. Headers wrap to two lines with their full names; the whole header cell sorts and the ⓘ sits inline: nothing is cut off and columns did not need to double in width.
62. Forecast view: one horizon at a time on phones (1W | 1M | 3M | 6M chips, compact widths, headers without the horizon); all four on desktop, where the Screener page uses a wider layout.
63. One explanations file (`web/src/lib/columnDocs.ts`) feeds both the ⓘ tooltips and the Columns explained page; a test fails if a column lacks any of the 8 parts.
64. Column groups follow your 10 groups, and labels use plain words ("Chance up 6M", "Return 1 month") instead of codes ("P(up) 6m", "1m").

## Questions for the owner

All optional. The site works without them.

1. **Your holdings** (daily refresh and alerts for what you own): GitHub → repo **Settings →
   Secrets and variables → Actions → Variables → New repository variable**, name `HOLDINGS`,
   value e.g. `AAPL, MSFT`. Also enter them on the site's *My portfolio* page (shares and cost).
2. **Telegram alerts**: in Telegram open **@BotFather** → `/newbot` → copy the token → send your
   bot any message → open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy
   `"chat":{"id": …}` → add secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
   (Settings → Secrets and variables → Actions → New repository secret).
3. **Ratings from Zacks / TipRanks / Seeking Alpha / Morningstar** (never scraped): in the private
   data repo create `manual/ratings/<source>.csv` with `ticker,rating,date` (1 = best … 5 = worst).
   Each file becomes one more F1 opinion source; ratings older than 45 days are ignored.
4. **Danelfin**: if you get an API key, add the secret `DANELFIN_API_KEY`.
5. **AI news extraction (paid)**: only if you want it, add `ANTHROPIC_API_KEY` and set a monthly
   limit in the Anthropic console. The extraction layer itself is not built yet.
6. **Privacy**: the site is public to anyone who has the URL (search engines are blocked). For a
   login, move to Cloudflare Pages + Cloudflare Access (free): SETUP.md, "Host on Cloudflare
   Pages" and "Put the site behind a login".
7. **Yahoo terms**: Yahoo data is for personal use; it stays private and only derived numbers are
   shown. Confirm you are fine with that, or name a paid source to switch to.
8. **Data repo size**: ≈ 0.5 GB now, ≈ +0.3 GB a year. Near 1 GB, old snapshots should move to
   Cloudflare R2 (free 10 GB, needs a Cloudflare account).
9. **Spec PDF**: `docs/ConvergeAlpha_v3_Final_Specification.pdf` was never in the folder.
   Everything follows the build prompt; add the PDF if you want it cross-checked.
10. **finanzen.net zero list check** (optional): the app uses gettex's official list, the only
    venue the broker uses. If the broker app ever disagrees (a stock marked buyable that you
    cannot buy, or the reverse): ask finanzen.net zero customer service (contact form in the app
    or on the website) for the list of tradable US shares as CSV or Excel, or note the ISINs or
    tickers yourself, then in the **private data repo** create `manual/brokers/finanzen_zero.csv`
    with one column `isin` or `ticker` (example in SETUP.md, section F). It replaces the gettex
    list from the next daily run; delete the file to switch back.
11. **Faster broker-list mapping** (optional): free account at https://www.openfigi.com → sign up
    → *API Key* → copy it → GitHub repo **Settings → Secrets and variables → Actions → New
    repository secret**, name `OPENFIGI_API_KEY`. Only speeds up the weekly job.

## Known limits

- **No BUY labels yet.** With the fallback estimate (before models), R7/R8 cannot pass. With
  models, the trade probability is weak (out-of-sample AUC ≈ 0.52), so few or no stocks clear
  p̂ ≥ 55%. That is the system saying NO TRADE honestly, not a bug.
- **BUY labels are not validated** (see the table above). Labels keep their RESEARCH MODE badge.
- **F1/F2 history starts now.** The models will improve once months of analyst snapshots exist.
- **Survivorship bias**: free price history lacks most delisted stocks (hence the 50% haircut).
- **Late scheduled runs**: GitHub started the first scheduled runs 4–6 hours late (daily at
  03:07 UTC instead of 22:30, the 20:15 intraday check at 02:01). Results are the same, they
  just arrive later; an intraday check that fires after the close finds nothing to check. Use
  **Run workflow** if you need an update sooner.
- **Data drift** (Health page): `days_since_report` and `industry_mom` are above PSI 0.25 against
  the training data. The first is most likely the earnings-season timing (mid-October, just
  before Q3 reports); watch whether it fades after the reports.
- **Picks are research.** They are the strongest-looking stocks by the app's own numbers. Their
  live record starts with the first daily run that published them; the first result arrives 21
  trading days later. Until the live race shows they beat the S&P 500, the page keeps its
  RESEARCH MODE badge.
- **"How often right" understates uncertainty.** Past cases overlap in time and stocks move
  together, so the true range is wider than the ± shown (said on the site). Out of sample, the
  app's extreme probabilities were less reliable than its middle ones (for example, 6-month
  "up" calls of ~73% came true ~56% of the time); the table shows this rather than hiding it.
- **finanzen.net zero list = gettex's list.** The broker can still restrict a single stock
  (e.g. for regulatory reasons); a foreign company's ADR can be "No" although its home share is
  on gettex. Check in the broker app before trading.
- **SEC 13F** (full institutional holdings), FDA calendar and buyback history are not built
  (no free dated source); see docs/DATA_SOURCES.md.
- `make` isn't installed on this Windows PC; SETUP.md lists the equivalent commands.

## Next steps

1. Let the schedules run; the scorecard and baseline race fill as outcomes mature (1 week to
   6 months).
2. After ~3 months of analyst snapshots, add F1/F2 to the model features (new configuration →
   logged in the holdout record).
3. If Yahoo changes its API, add a backup source for prices and analyst data (Polygon, Alpha
   Vantage or FMP; their keys are listed on the Health page, the connectors are not built).
