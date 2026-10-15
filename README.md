# ConvergeAlpha

A personal, free, phone-friendly website that ranks US stocks by how likely they are to rise,
how much upside they have and how fast, and gives each stock a plain label (BUY, WATCH, HOLD,
ROTATE, SELL / RISK WARNING, NO TRADE) together with the exact numbers behind it.

> No tool can make a stock rise for sure. ConvergeAlpha puts the odds in your favour, shows
> exactly what each percentage promises, and says NO TRADE when the evidence is weak.
> Not financial advice.

| Document | What it covers |
|---|---|
| [PROGRESS.md](PROGRESS.md) | What works, what's next, known limits |
| [SETUP.md](SETUP.md) | Accounts, keys, hosting choices, free-tier limits |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Signals, models, labels and formulas |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Every data source, its terms and limits |

## Layout

```
pipeline/   Python 3.12: ingest -> features -> models -> forecasts -> JSON export
            (raw data lives in the private repo RayenSouissi45/convergealpha-data)
web/        React + TypeScript + Vite + Tailwind, static, mobile-first
docs/       methodology and data-source notes
.github/workflows/
  ci.yml        lint, types, unit + phone e2e tests on every push
  daily.yml     Mon-Fri 22:30 UTC: prepare -> 6 fetch shards + finnhub -> build -> deploy
  intraday.yml  every ~2 h in market hours: risk/event check for candidates and holdings
  live.yml      every minute in market hours: live values of the paper strategies (live branch)
  weekly.yml    Saturday: XBRL refresh, finanzen.net zero list, retrain walk-forward,
                "how often right" tables, validation lab, keep-alive
  deploy.yml    build the site and publish (GitHub Pages or Cloudflare Pages)
  backfill.yml / bootstrap.yml   one-time history loads
```

## Run it locally

Windows (PowerShell):

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e "pipeline[dev]"
python -m convergealpha demo        # 30 stocks, < 5 minutes, writes web/public/data
cd web; npm ci; npm run dev          # http://localhost:5173
```

Linux/macOS: `make install && make demo && make dev`. Tests: `make check` (or `pytest` in `pipeline/` and
`npm test && npm run e2e` in `web/`).
