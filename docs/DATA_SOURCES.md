# Data sources

Each source's current limits and terms are checked **when it is integrated** and recorded here
with the date. Until then the row says "not yet integrated".

## Rules

1. Official APIs, or libraries meant for programmatic access. **No scraping** of sites that
   forbid it (Zacks, TipRanks, Seeking Alpha, Morningstar and similar). Where no permitted free
   source exists, the app gets a **plugin slot**, disabled by default, or a manual CSV import.
2. Store `source`, `as_of` (publication time) and `retrieved_at` for every value.
3. Append-only daily snapshots of every rating, estimate and score; never overwrite history.
4. Throttle and retry politely; cache aggressively. SEC: at most 10 requests/second with a
   descriptive User-Agent (`SEC_USER_AGENT`).
5. Never delete a ticker once seen (limits survivorship bias).
6. **Redistribution.** Some free tiers allow personal use only. Raw data from those sources is
   not republished in bulk; see SETUP.md section 2 for where raw snapshots are stored.

## Sources

| Need | Source | Phase | Status |
|---|---|---|---|
| Universe | SEC `company_tickers_exchange.json`; Nasdaq Trader `nasdaqlisted.txt` / `otherlisted.txt` | 1 | Not yet integrated |
| Daily prices | `yfinance` batch download; optional Polygon grouped daily | 1 | Not yet integrated |
| Analyst consensus, targets, rating changes | `yfinance`; Finnhub recommendation trends | 2 | Not yet integrated |
| EPS estimates and revisions | `yfinance` (eps_trend, eps_revisions, revenue estimates) | 2 | Not yet integrated |
| Earnings history and calendar | Finnhub; `yfinance` earnings dates | 2 | Not yet integrated |
| Insider trades | SEC EDGAR Form 4 (daily index → new Form 4 XML) | 2 | Not yet integrated |
| Institutional ownership | SEC 13F (quarterly); `yfinance` holders meanwhile | 2 | Not yet integrated |
| Fundamentals (point-in-time) | SEC XBRL companyfacts API (`filed` dates) | 2 | Not yet integrated |
| Short interest | FINRA short-interest files; FINRA daily short-sale volume | 2 | Not yet integrated |
| Options | `yfinance` option chains | 2 | Not yet integrated |
| News and filings | Finnhub company news; SEC 8-K feed | 2 | Not yet integrated |
| Macro and regime | FRED: VIXCLS, BAMLH0A0HYM2, T10Y2Y, fed funds | 2 | Not yet integrated |
| Market benchmark | S&P 500 index level and total-return proxy | 1 | Not yet integrated |
| Third-party ratings | Danelfin API (if key); Zacks / TipRanks / SA Quant / Morningstar only as disabled plugin slots or manual CSV import | 2 | Not yet integrated |

## Notes gathered so far (2026-10-12, not yet re-verified at integration)

- **Finnhub free tier:** reported by third parties as about 60 calls/minute, personal and
  non-commercial use, no card required. To be confirmed on finnhub.io/pricing in phase 2.
- **FRED:** a free API key from fredaccount.stlouisfed.org; one key per application is advised.
