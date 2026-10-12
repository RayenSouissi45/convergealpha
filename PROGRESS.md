# Progress

Last updated: 2026-10-12

| Phase | Deliverable | Status |
|---|---|---|
| 0 Setup | Repo, CI, SETUP.md, empty site deployed | Built and tested locally; **waiting for GitHub login to deploy** |
| 1 Universe + prices + screener | ≥ 5,000 stocks, daily prices, screener, stock page | Not started |
| 2 Evidence data | Analysts, estimates, earnings, insiders, fundamentals, short interest, options, regime, news | Not started |
| 3 Families + labels | F1–F7, labels, position plan, Today page | Not started |
| 4 Models + forecasts | L0–L3, 4-horizon forecasts, analogs, event patterns | Not started |
| 5 Validation lab | /validation report | Not started |
| 6 Ledger + monitoring | Hash-chained ledger, scorecard, kill switch, Telegram | Not started |
| 7 Polish | PWA, Lighthouse ≥ 90, docs | Not started |

Live URL: not deployed yet (see "Waiting on you").

## Phase 0: what works

**Pipeline** (`pipeline/`, Python 3.12)
- `python -m convergealpha daily --out <dir>` runs every implemented step. In phase 0 that is
  only `health.json`: run time, link to the GitHub run, build phase, status of each of the 12
  planned data sources ("not connected yet"), and which API keys are set (never their values).
- The spec's core formulas are already implemented and tested against every reference value in
  section 13 that doesn't need market data: robust sector normalization, N_eff (1.5 / 2.5),
  Wilson (230/400 → 52.6–62.3%), costs (0.29%), Kelly (23.1%), sizing (5 shares), planned exit,
  gap stress, EV, fallback P(up). The 16:15 New York decision cutoff is in `config.py`.
- 28 tests; ruff and strict mypy are clean.

**Website** (`web/`, React 19 + TypeScript + Vite + Tailwind)
- All pages from section 11 exist: Today, Screener, Stock, Compare, My portfolio, Scorecard,
  Baseline race, Validation, Health, About & method, plus a phone "More" menu.
- Health shows the live pipeline report. The other pages say what they will show and in which
  phase; they never show sample numbers.
- Global RESEARCH MODE banner, "data may be out of date" banner (no update for 3.5 days), and
  kill-switch banner (inactive until phase 6).
- Missing values are "—" and explain why on tap (phones) or hover.
- Mobile-first: bottom tab bar with 44 px+ tap targets, no horizontal scroll, dark/light/auto
  theme, colours always paired with text.
- Hash routing (`/#/health`), so the same build works on GitHub Pages and Cloudflare Pages.
- 17 unit tests (every page renders, health states, banners, tooltip) and 24 Playwright checks at
  phone (Pixel 7) and desktop sizes (no horizontal scroll, no console errors, nav works, tooltips
  stay on screen). JS bundle: 92 KB gzipped.

**Automation** (`.github/workflows/`, checked with actionlint)
- `ci.yml`: pipeline lint + types + tests; web lint + types + tests + build + phone e2e.
- `daily.yml`: Mon–Fri 22:30 UTC → pipeline → deploy. Also runnable by hand.
- `deploy.yml`: builds and publishes to GitHub Pages (default) or Cloudflare Pages
  (`DEPLOY_TARGET=cloudflare`). Website-only pushes redeploy using the latest daily data.

## Waiting on you

1. **Log in the GitHub CLI** (SETUP.md section 1).
2. **Public or private repo** (SETUP.md section 2; public is recommended).

Then Claude Code creates the repo, enables Pages, pushes, runs the first daily job and gives you
the URL.

## Decisions needed before phase 1

- **Where raw data snapshots live:** a `data` branch in this repo (spec default; public if the
  repo is public) or a private `convergealpha-data` repo (recommended if the code repo is public,
  because some free data is licensed for personal use only). See SETUP.md section 2.
- **`SEC_USER_AGENT` e-mail:** which contact e-mail to send to the SEC.

## Known limits

- No market data yet; that starts in phase 1.
- `docs/ConvergeAlpha_v3_Final_Specification.pdf` was not in the folder, so everything follows
  the build prompt. Add the PDF to `docs/` and it will be cross-checked.
- `intraday.yml` and `weekly.yml` are not created yet. They are added when they have work to do
  (weekly in phase 2, intraday in phase 3), so empty scheduled jobs don't run for nothing.
- Not yet an offline PWA (phase 7); "Add to Home Screen" works as a shortcut.
- `make demo` (30 tickers in < 5 minutes) arrives with phase 1. GNU make isn't installed on this
  Windows machine; the README lists the equivalent commands.
- Page URLs use a hash (`/#/validation` rather than `/validation`) so they work on any static
  host without server rules.

## Next: phase 1 plan

1. Universe: SEC `company_tickers_exchange.json` + Nasdaq Trader lists → common stocks on
   NYSE / Nasdaq / NYSE American; ETFs, funds, warrants, units, preferreds and rights excluded;
   every ticker ever seen kept.
2. Prices: 10-year adjusted history backfill (split across runs to stay under ~40 minutes),
   then daily incremental updates; split, zero-price and stale-feed checks.
3. Features: 1w / 1m / 3m / YTD / 1y returns, volatility, ATR, 50/200-day trend, distance from
   the 52-week high, liquidity (average daily traded value).
4. Exports: `screener.json` (compact rows), `stocks/<TICKER>.json`, `health.json` with real
   freshness.
5. Website: virtualized screener (TanStack Table) that scrolls 5,000+ rows on a phone, search,
   sorting, column chooser, liquidity greying; stock page with a `lightweight-charts` price chart.
6. Append-only daily Parquet snapshots; `make demo`; leakage and data-quality tests.
