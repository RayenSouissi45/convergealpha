# Setup

Everything here is free. Terms and limits were checked on **2026-10-12** (sources at the end).

## What is already set up

| Item | Status |
|---|---|
| Code repository | `RayenSouissi45/convergealpha` (public) |
| Private data repository | `RayenSouissi45/convergealpha-data` (raw data, snapshots, ledger) |
| Website | https://rayensouissi45.github.io/convergealpha/ (GitHub Pages, deployed by Actions) |
| Secrets | `SEC_USER_AGENT`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `DATA_DEPLOY_KEY` (write access to the data repo only) |
| Variables | `DATA_REPO = RayenSouissi45/convergealpha-data` |
| Schedules | daily (Mon–Fri 22:30 UTC), intraday (about every 30 minutes in US market hours), live strategy values (every minute in US market hours; starters every 20 minutes from 13:07 UTC, and from each intraday run), weekly (Saturday 06:00 UTC) |

Your API keys exist only as GitHub Actions secrets and in your local `.env` (gitignored). They are
never written to logs, the data repo or the website (the Health page shows only "Set / Not set").

---

## Optional: things only you can add

All of these are optional; the app works without them and the Health page says what is missing.

### A. Your holdings (daily refresh + alerts for the stocks you own)

Your portfolio itself stays in your browser. To have the pipeline refresh your holdings every day
(analyst data, options, news) and warn you about them:

1. GitHub → your repo → **Settings → Secrets and variables → Actions → Variables** tab →
   **New repository variable**.
2. Name `HOLDINGS`, value: your tickers separated by commas, e.g. `AAPL, MSFT, NVDA`.
   (Visible to anyone who can read the repo's settings — only you.)

### B. Telegram alerts (new Top Conviction, exits for your holdings, kill switch)

1. In Telegram, open **@BotFather** → `/newbot` → pick a name and a username ending in `bot` →
   copy the token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and find
   `"chat":{"id": <number>` — that number is your chat ID.
4. Add secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (Settings → Secrets and variables →
   Actions → New repository secret, or `gh secret set TELEGRAM_BOT_TOKEN`).

### C. AI news event extraction (costs money: optional)

Add `ANTHROPIC_API_KEY` (from https://console.anthropic.com → API keys) **and** set a monthly
spend limit in the Anthropic console (Settings → Limits). Without it, news uses the
Loughran–McDonald word lists and keyword tags, which is free. The AI layer is not built yet; see
PROGRESS.md.

### D. Danelfin score

If Danelfin offers you an API key, add it as `DANELFIN_API_KEY`. The slot stays disabled without
it.

### E. Ratings from sites that forbid scraping (Zacks, TipRanks, Seeking Alpha, Morningstar)

The app never scrapes them. You can add ratings by hand: create
`manual/ratings/<source>.csv` in the **private data repo** (e.g. `manual/ratings/zacks.csv`):

```csv
ticker,rating,date
AAPL,2,2026-10-12
NVDA,1,2026-10-12
```

Rating 1 = best … 5 = worst. Each file becomes one more opinion source in F1 (ratings older than
45 days are ignored).

### F. finanzen.net zero list (works without you; optional fixes)

The weekly job builds the list itself from gettex's official instrument list (ESMA FIRDS), the
only venue finanzen.net zero uses. Two optional extras:

- **Faster ISIN mapping**: create a free OpenFIGI account at https://www.openfigi.com → sign up →
  *API Key* → copy it, then add it as the secret `OPENFIGI_API_KEY`. Without it the first full
  mapping takes ~35 minutes (it was already done on 2026-10-13); later weeks only map new ISINs.
- **Your own list instead** (if the broker gives you one, e.g. from the app or customer service):
  put `manual/brokers/finanzen_zero.csv` in the **private data repo** with a column `isin` or
  `ticker`:

  ```csv
  isin
  US0378331005
  US5949181045
  ```

  It replaces the FIRDS list from the next daily run; delete the file to go back.

---

## Optional: host on Cloudflare Pages instead (needed to put the site behind a login)

1. Create a free account at https://dash.cloudflare.com/sign-up.
2. In a terminal: `npx wrangler login`, then
   `npx wrangler pages project create convergealpha --production-branch main`.
3. Cloudflare dashboard → **Account API tokens** → **Create Token** → **Custom Token → Get
   started** → Permissions: **Account · Cloudflare Pages · Edit** → **Continue to summary** →
   **Create Token** → copy it.
4. Your **Account ID** is on the **Workers & Pages** overview page (right-hand column).
5. GitHub → Settings → Secrets and variables → Actions: secrets `CLOUDFLARE_API_TOKEN` and
   `CLOUDFLARE_ACCOUNT_ID`; variable `DEPLOY_TARGET` = `cloudflare`.
6. Actions → **deploy** → **Run workflow**. The site moves to https://convergealpha.pages.dev.

Switch back by setting `DEPLOY_TARGET` to `github-pages` (or deleting it).

### Put the site behind a login (Cloudflare Access, free up to 50 users)

Needs Cloudflare hosting (above); Access cannot protect a `github.io` address.

1. Cloudflare dashboard → **Workers & Pages** → your project → **Settings** → **Enable access
   policy** (this alone protects only preview deployments).
2. **Manage** on that policy → **Access → Applications** → your project → **Configure**.
3. Under **Public hostname**, delete the `*` from **Subdomain** and **Save** (rename the
   application if it complains): this protects `convergealpha.pages.dev`.
4. Back in the Pages project, **Enable access policy** again to re-protect previews.
5. Keep the policy to your e-mail only (Include → Emails). You log in with a one-time code.

---

## Running it yourself

| What | How |
|---|---|
| A daily run now | GitHub → **Actions → daily → Run workflow** |
| Retrain the models now | **Actions → weekly → Run workflow** (≈ 15–30 minutes) |
| An intraday check now | **Actions → intraday → Run workflow** |
| Start the live strategy values now | **Actions → live → Run workflow** |
| Re-download price history | **Actions → backfill → Run workflow** |
| Re-load SEC / FINRA history | **Actions → bootstrap → Run workflow** |
| Local demo (30 stocks, < 5 min) | `python -m convergealpha demo` then `cd web && npm run dev` (or `make demo` on Linux/macOS) |

Local development on Windows:

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e "pipeline[dev]"
python -m convergealpha demo          # writes web/public/data
cd web; npm ci; npm run dev            # http://localhost:5173
```

---

## Free-tier limits (checked 2026-10-12)

**GitHub Actions**: standard GitHub-hosted runners are free in public repositories (private
repositories on GitHub Free: 2,000 minutes/month, 500 MB artifacts, blocked when used up). A job
can run at most 6 hours. Scheduled workflows in public repositories are disabled after 60 days
without repository activity; the weekly job re-enables the schedules every week.

**GitHub Pages**: free for public repositories (private ones need Pro/Team/Enterprise); site
≤ 1 GB, soft bandwidth 100 GB/month, deployments time out after 10 minutes; the 10-builds-per-hour
soft limit does not apply to custom Actions workflows.

**Private data repository**: no fixed quota, but GitHub recommends repositories stay under 1 GB
(5 GB strongly). Current size is about 0.5 GB and grows roughly 0.3 GB a year (daily snapshots).
When it nears 1 GB, move `snapshots/` to Cloudflare R2's free tier (10 GB) or prune old
analyst snapshots after archiving them.

**Cloudflare Pages (Free)**: 20,000 files per site (we ship about 5,400 stock files), 25 MiB per
file, 500 builds/month (we upload pre-built files). **Cloudflare Zero Trust**: free for up to 50
users.

## Optional paid upgrades

None needed. The only feature that costs money is the AI news layer (Anthropic API, pay-as-you-go;
set a spend limit). Everything else runs on free tiers.

## Sources

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub: disabling and enabling workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits)
- [Cloudflare Pages direct upload with CI](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)
- [Cloudflare Pages known issues (Access on pages.dev)](https://developers.cloudflare.com/pages/platform/known-issues/)
- [Cloudflare Zero Trust plans](https://blog.cloudflare.com/teams-plans)
- [FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html)
- [Loughran–McDonald Master Dictionary](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)
