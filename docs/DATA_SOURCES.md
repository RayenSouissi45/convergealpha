# Data sources

Checked on **2026-10-12** while integrating each source. Raw data is stored only in the private
repository `convergealpha-data`; the public website shows derived numbers.

## Rules

1. Official APIs, or libraries meant for programmatic access. **No scraping** of sites that
   forbid it (Zacks, TipRanks, Seeking Alpha, Morningstar…). Where no permitted free source
   exists there is a **disabled plugin slot** or a manual CSV import (below).
2. Every stored value keeps its source and time: `as_of` / filing / publication date and the
   download time (`basis`, `fetched_at`, `retrieved_at`).
3. A value is used for trading day D only if it was public before D at 16:15 New York time
   (bars are never stored before the close; SEC data by filing date; FINRA by publication date).
4. Append-only storage: daily files are added, never rewritten (prices, filings, insider trades,
   analyst snapshots, events, scores, ledger).
5. Throttled and retried politely: SEC ≤ 8 requests/second with a contact User-Agent; Finnhub
   ≤ 0.9 calls/second; Yahoo ≈ 2.5 requests/second per runner.
6. Every ticker ever seen is kept (universe history), but free sources lack most delisted
   stocks, so backtests still have survivorship bias: all backtested excess returns are halved
   before they are shown.

## Sources in use

| Need | Source | Access, limits, terms | Refresh | Since |
|---|---|---|---|---|
| Universe | Nasdaq Trader `nasdaqlisted.txt`, `otherlisted.txt`; SEC `company_tickers_exchange.json` | Public files, no key. SEC fair-access policy: ≤ 10 req/s with a contact User-Agent | Daily | Snapshots from 2026-10-12 |
| Daily prices (OHLCV, dividends, splits) | Yahoo Finance via `yfinance` (1.7) | Unofficial API, no key. Yahoo terms allow personal use; no redistribution of raw data. Rate limits are unpublished: downloads are sharded across runners and throttled | Daily (6 parallel shards) | 2010-01-01 |
| Analyst consensus, targets, recommendation counts, rating-change history, EPS/revenue estimate trends and revisions, earnings calendar and history, institutional holders, short interest (Yahoo copy) | Yahoo `quoteSummary` via `yfinance` (one call per ticker) + earnings dates | As above | 1/5 of the universe per day + daily for the ~400 top candidates, holdings and stocks near earnings | Snapshots from 2026-10-12; rating changes ≈ 3 years back; earnings dates ≈ 6 years back |
| Options implied volatility | Yahoo option chains via `yfinance` | As above | Daily for top candidates and holdings | Live only |
| Recommendation trends, earnings calendar, company news | Finnhub free tier (`FINNHUB_API_KEY`) | 60 calls/minute; personal, non-commercial use. Price targets and upgrades/downgrades are **premium** (HTTP 403) on the free tier, so those come from Yahoo | Calendar daily; trends for candidates + a rotating 1/10; news for top candidates | Live |
| Insider trades (Form 4) | SEC Insider Transactions Data Sets (quarterly ZIP) + Form 4 XML from the EDGAR daily index | Official, public domain. Pre-2023 data sets have no 10b5-1 checkbox column; plan trades are then found from footnotes | New quarters weekly; Form 4 XML daily | 2010 Q1 |
| Fundamentals | SEC XBRL company facts (bulk `companyfacts.zip` weekly + per-company API after new 10-K/10-Q) | Official, public domain. Only US-GAAP facts; IFRS filers (some foreign companies) have no F6 yet | Weekly + after each new filing | 2009 (as first reported) |
| Company data, filings, 8-K items | SEC submissions API + daily form index; EDGAR live feed (intraday) | Official | Daily for new filers, monthly rotation for the rest | ≈ 400 days of relevant filings |
| Short interest | FINRA equity short interest files (`cdn.finra.org`, twice monthly) | Public files; missing dates return HTTP 403. Used only from an estimated publication date (settlement + 8 trading days) | Twice monthly | 2019-01 |
| Macro / regime | FRED API (`FRED_API_KEY`): VIXCLS, BAMLH0A0HYM2, T10Y2Y, DFF | Free key; the ICE BofA high-yield series is copyrighted by ICE Data Indices: personal use only | Daily | 2009 |
| EUR/USD (euro amounts, paper trading) | FRED API: DEXUSEU (Federal Reserve H.10, US dollars per euro) | Free key; public-domain Fed data | Published about weekly (daily values) | 2009 |
| Benchmark | SPY (total-return proxy, via Yahoo) and ^GSPC (price index for the 200-day rule) | As Yahoo | Daily | 2010 |
| finanzen.net zero availability | ESMA FIRDS full equity files (`FULINS_E_*.zip`, listed by the FIRDS register API) filtered to gettex (MIC MUND/MUNC) shares and ADRs; ISINs mapped to tickers with the OpenFIGI API | Official EU reference data, free; reuse authorised with the source acknowledged. OpenFIGI: free, identifiers public domain; 25 requests/minute × 10 ISINs without a key (optional `OPENFIGI_API_KEY`: 25 requests/6 s × 100). The list is checked against the broker's own claim (≈ 8,600 gettex shares/ADRs vs "more than 8,500 shares") | Weekly (Saturday) | Live only |
| News tone | Loughran–McDonald sentiment word lists (Notre Dame SRAF) | Free for academic/non-commercial research; kept **only in the private data repo**, never published | Static | 1993–2023 release |

## Not connected (and why)

| Source | Status | What would connect it |
|---|---|---|
| Danelfin AI score | Plugin slot, disabled | Add a `DANELFIN_API_KEY` secret (free tier if available) |
| AI news event extraction (Anthropic) | Disabled | Add `ANTHROPIC_API_KEY`; keyword tags + Loughran–McDonald are used instead |
| Zacks, TipRanks, Seeking Alpha Quant, Morningstar | Disabled plugin slots — their terms forbid scraping | Manual CSV import: put `manual/ratings/<source>.csv` (columns `ticker,rating,date`, rating 1 = best … 5 = worst) in the data repo |
| SEC 13F (full institutional holdings) | Not built | Yahoo's top-holder position changes are used for F4 meanwhile |
| FDA / PDUFA calendar | No free official calendar | FDA-related news tags are shown as information |
| Polygon, Alpha Vantage, FMP | Not needed | Optional backups if Yahoo becomes unreliable |
| Index inclusion, buyback announcements, guidance history | No free dated history | Not tested by the event-pattern engine |
