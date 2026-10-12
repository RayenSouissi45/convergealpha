# Setup

Everything here is free. Steps marked **(you)** need your own accounts; Claude Code does the rest.
Terms and limits below were checked on **2026-10-12** (sources at the end).

---

## 1. Log the GitHub CLI into your account (you, about 2 minutes)

No GitHub account yet? Create one at <https://github.com/signup> first.

1. In VS Code, open a terminal: menu **Terminal → New Terminal**.
2. Run `gh auth login`.
3. Answer the prompts: **GitHub.com** → **HTTPS** → **Yes** (authenticate Git with your GitHub
   credentials) → **Login with a web browser**.
4. Copy the 8-character code it prints, press **Enter**, paste the code in the browser page that
   opens, and click **Authorize**.
5. Check with `gh auth status`. It should say `Logged in to github.com account <your-name>`.

Then tell Claude Code "logged in" and it will do step 3.

---

## 2. Choose public or private code (you)

| | **Public repo + GitHub Pages** (recommended) | Private repo + Cloudflare Pages |
|---|---|---|
| Hosting | Free | Free |
| GitHub Actions minutes | Free and unlimited on standard runners | 2,000 per month; jobs stop when used up (no card on file) |
| Who can see the code and stored data | Anyone | Only you |
| Website address | `https://<your-name>.github.io/convergealpha/` | `https://convergealpha.pages.dev` |
| Put the website behind a login later | Switch hosting to Cloudflare (one variable) + Cloudflare Access | Cloudflare Access |
| Extra accounts | None | Cloudflare (free) |

**Recommendation: public.** The pipeline will need roughly 900 minutes a month for the daily
runs alone (about 40 minutes × 22 trading days), plus the intraday checks, the weekly retraining
and walk-forward validation, and CI. A private repo would hit the 2,000-minute cap and the
updates would stop until the next month. Public repos have no cap for standard runners.

What "public" means in practice:

- Anyone can read the code. Nobody can change it without your permission.
- The website is reachable by anyone who has the URL (it is not listed anywhere). Your portfolio
  and capital are **never** uploaded; they stay in your phone's browser storage.
- **Decision before phase 1:** where to keep raw downloaded data. Some providers (for example
  Yahoo through `yfinance`, and Finnhub's free tier) allow personal use but not
  redistribution, and a `data` branch in a public repo is effectively redistribution. Options:
  (a) the spec's `data` branch in this repo, or (b) a second, **private** repo
  `convergealpha-data` that the public repo's workflows write to with a fine-grained token
  (still free; Actions minutes are charged to the public repo where the workflow runs).
  Claude Code will ask you before phase 1 writes its first snapshot.

---

## 3. Create the repository and turn on Pages (Claude Code does this)

Once you are logged in, Claude Code runs:

```bash
gh repo create convergealpha --public --source=. --remote=origin
gh api -X POST repos/<your-name>/convergealpha/pages -f build_type=workflow   # Pages from Actions
git push -u origin main
gh workflow run daily.yml                                                       # first data + deploy
```

If you prefer clicking:

1. <https://github.com/new> → Repository name `convergealpha` → **Public** → leave "Add a
   README" unticked → **Create repository**.
2. In the new repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Push the code (`git remote add origin https://github.com/<your-name>/convergealpha.git`,
   then `git push -u origin main`).
4. **Actions** tab → **daily** → **Run workflow**.

The site appears at `https://<your-name>.github.io/convergealpha/` about 2 minutes later.

---

## 4. Add API keys as secrets (you, about 10 minutes; needed from phase 1–2)

Where: your repo → **Settings → Secrets and variables → Actions → New repository secret**.
Or in the terminal: `gh secret set NAME` (it asks for the value and never displays it).

The app runs without any optional key; the Health page shows which ones are set (never their
values).

| Secret | Needed | How to get it |
|---|---|---|
| `SEC_USER_AGENT` | **Required from phase 1** | No sign-up. Value: `ConvergeAlpha your-real-email@example.com`. SEC EDGAR asks automated tools to identify themselves with a contact e-mail. |
| `FINNHUB_API_KEY` | Recommended (phase 2) | <https://finnhub.io/register> → sign up with e-mail → confirm → the key is on your dashboard. Free tier is for personal use (about 60 calls/minute). |
| `FRED_API_KEY` | Recommended (phase 2) | Create an account at <https://fredaccount.stlouisfed.org>, log in, open <https://fredaccount.stlouisfed.org/apikeys> → **Request API Key** → describe it as "personal research dashboard" → copy the 32-character key. |
| `POLYGON_API_KEY` | Optional | Free key from polygon.io (grouped daily prices). |
| `ALPHAVANTAGE_API_KEY`, `FMP_API_KEY` | Optional | Free keys; backup data only. |
| `DANELFIN_API_KEY` | Optional | Danelfin API (free tier, if available) for a third-party score. |
| `ANTHROPIC_API_KEY` | Optional (phase 2+) | <https://console.anthropic.com> → API keys. Also set a monthly spend limit there; the app enforces its own budget cap too. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional (phase 6) | See "Optional C" below. |

---

## 5. Open it on your phone

Open the site URL in your phone's browser. To get an app icon: **iPhone (Safari)** Share →
**Add to Home Screen**; **Android (Chrome)** ⋮ menu → **Add to Home screen**. Full offline
support comes in phase 7.

---

## Optional A: host on Cloudflare Pages instead of GitHub Pages

Use this for a private repo, or to put the site behind a login (Optional B).

1. Create a free account at <https://dash.cloudflare.com/sign-up>.
2. Create the Pages project once, in a terminal: `npx wrangler login`, then
   `npx wrangler pages project create convergealpha --production-branch main`.
3. Create an API token: Cloudflare dashboard → **Account API tokens** → **Create Token** →
   **Custom Token → Get started** → Permissions: **Account · Cloudflare Pages · Edit** →
   **Continue to summary** → **Create Token** → copy it.
4. Find your **Account ID**: on the **Workers & Pages** overview page, in the right-hand column.
5. In GitHub → **Settings → Secrets and variables → Actions**:
   - **Secrets** tab: add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
   - **Variables** tab: add `DEPLOY_TARGET` = `cloudflare` (and `CLOUDFLARE_PROJECT` if you
     named the project something other than `convergealpha`).
6. **Actions → deploy → Run workflow**. The site is at `https://convergealpha.pages.dev`.

Switch back any time by setting `DEPLOY_TARGET` to `github-pages` (or deleting it).

## Optional B: lock the site behind a login (Cloudflare Access, free up to 50 users)

This needs Cloudflare hosting (Optional A); Access cannot protect a `github.io` address.

1. Cloudflare dashboard → **Workers & Pages** → your project → **Settings** → **Enable access
   policy**. (By itself this only protects preview deployments.)
2. Select **Manage** on the Access policy it created → under **Access → Applications** select
   your project → **Configure**.
3. Under **Public hostname**, delete the wildcard `*` from the **Subdomain** field and **Save**
   (rename the application if it complains). This now protects `convergealpha.pages.dev`.
4. Back in the Pages project settings, select **Enable access policy** again to re-protect
   previews. You should now see two Access policies.
5. Make sure the policy allows only your e-mail (Include → Emails). You log in with a one-time
   code sent to that address.

## Optional C: Telegram alerts (used from phase 6)

1. In Telegram, open **@BotFather** → `/newbot` → pick a name and a username ending in `bot` →
   copy the token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and find
   `"chat":{"id": <number>` — that number is the chat ID.
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as secrets. Alerts stay off until both exist.

---

## Free-tier limits (checked 2026-10-12)

**GitHub Actions**
- Standard GitHub-hosted runners are free in public repositories.
- Private repositories on GitHub Free: 2,000 minutes/month and 500 MB artifact storage; without
  a payment method, usage is blocked once the quota is used.
- One job can run at most 6 hours.
- In public repositories, scheduled workflows are disabled automatically after 60 days without
  repository activity. Daily data commits (from phase 1) should count as activity. If GitHub
  ever disables the schedule, re-enable it on the Actions tab. A keep-alive is planned for the
  weekly job.

**GitHub Pages**
- Free for public repositories; private repositories need GitHub Pro, Team or Enterprise.
- Published site at most 1 GB; soft bandwidth limit 100 GB/month; a deployment times out after
  10 minutes. The 10-builds-per-hour soft limit does not apply to custom Actions workflows
  (which we use).

**Cloudflare Pages (Free)**
- Up to 20,000 files per site (we will ship about 6,000 stock files) and 25 MiB per file.
- 500 builds/month. We upload already-built files from GitHub; even counted as builds, 1–3
  deploys per day stay far below that.
- Cloudflare now also promotes Workers static assets for new projects; Pages is still supported.

**Cloudflare Zero Trust (Access)**: free for up to 50 users.

## Optional paid upgrades

None needed so far. Anything that would cost money will be listed here with its price, and the
app will keep working without it.

## Sources

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub: disabling and enabling workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [GitHub Actions pricing update, Dec 2025](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits)
- [Cloudflare Pages direct upload with CI](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)
- [Cloudflare Pages known issues (Access on pages.dev)](https://developers.cloudflare.com/pages/platform/known-issues/)
- [Cloudflare Workers vs Pages](https://developers.cloudflare.com/workers/static-assets/compatibility-matrix)
- [Cloudflare Zero Trust plans](https://blog.cloudflare.com/teams-plans)
- [FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html)
