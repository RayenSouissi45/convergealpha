# Methodology

This file explains how ConvergeAlpha turns data into labels and probabilities. It grows with each
build phase; the **Status** column says what is implemented today. The reference is the build
prompt (and `docs/ConvergeAlpha_v3_Final_Specification.pdf` once added; where they differ, the
prompt wins).

**Honesty principle.** No tool can make a stock rise for sure. The app puts the odds in your
favour, shows exactly what each percentage promises, and says NO TRADE when the evidence is weak.
Every probability carries a "RESEARCH MODE — not yet validated" badge until the validation lab
(section 9) passes for that horizon or label.

## Status by section

| Section | Status |
|---|---|
| Point-in-time data rule (16:15 New York decision time) | Implemented: `config.decision_cutoff` |
| Core formulas (normalization, Wilson, N_eff, costs, EV, Kelly, sizing, fallback P(up)) | Implemented with reference tests: `pipeline/src/convergealpha/core/stats.py` |
| Universe, prices, returns, volatility, trend | Phase 1 |
| Evidence data (analysts, estimates, earnings, insiders, fundamentals, short interest, options, macro, news) | Phase 2 |
| Families F1–F7, N_eff, disagreement, regime, blocking events, labels, position plan | Phase 3 |
| Models L0–L3, per-horizon forecasts, conformal ranges, analogs, event patterns | Phase 4 |
| Validation lab | Phase 5 |
| Ledger, scorecard, baseline race, kill switch, alerts | Phase 6 |

## Point-in-time rule

Every stored value keeps `source`, `as_of` (when it was published) and `retrieved_at`. A value can
influence the decision for trading day D only if `as_of` is before **D at 16:15 New York time**.
Build-time leakage tests (phase 1+) fail the build if any feature breaks this rule, or if the
holdout period is evaluated more than once.

## Implemented formulas

All rates are fractions (0.0029 = 0.29%).

### Signal normalization (section 4)

For each raw signal across the universe on one day:

1. Winsorize at the universe 1st and 99th percentiles.
2. Robust z within the sector: `z = (x − median_sector) / (1.4826 · MAD_sector)`, clipped to [−3, 3].
3. `score = 100 · Φ(z)`.

Implementation choices not fixed by the spec:
- Missing values stay missing (shown as "—"); they are never imputed into a score.
- A sector with fewer than 5 valid values, or with zero spread (MAD = 0), uses the universe-wide
  median and MAD. If the universe spread is also zero, every score is 50.

### Effective number of independent sources (section 4)

`N_eff = (Σw)² / ΣΣ w_i w_j ρ_ij`. Reference tests: 6 equal sources at ρ = 0.6 → 1.5;
4 at ρ = 0.2 → 2.5.

### Wilson interval (section 5)

95% Wilson score interval for k successes out of n. Reference test: 230/400 = 57.5%
(52.6%–62.3%).

### Trading costs and expected value (section 5)

`C = spread + 2·commission + 2·impact`, with `impact = 0.5 · σ_daily · √(order / ADV)`.
Reference test: σ 2%, order 1% of ADV, spread 0.05%, commission 0.02% → C = 0.29%.

`EV = p̂·W̄ − (1 − p̂)·L̄ − C`, with W̄ and L̄ taken from the same calibration bucket as p̂.

### Position sizing (section 7)

- Planned exit `X = max(E − 2·ATR, 0.92·E)` — always called the *planned exit level*, never the
  maximum loss, because prices can gap through it.
- Gap stress `G = E · |mean of the worst 2% overnight returns over 500 days|`.
- Risk per share `r = max(E − X, G)`.
- Shares `= 0.75% · equity · tier / r` (tier 1 = full, tier 2 = half), capped by ¼-Kelly on the
  Wilson lower bound (as a fraction of equity invested), 10% of equity, and 1% of ADV. Whole
  shares, rounded down.
- Kelly `f* = p − (1 − p)/b`. Reference tests: p 0.53, b 11/7 → 23.1%; equity $10,000, E $100,
  X $92, G $9 → 5 shares (the ¼-Kelly cap binds).

### Fallback probability before models are validated (section 5)

`P(up) ≈ Φ(((μ − σ²/2)·T) / (σ·√T))`, with T in years (252 trading days), μ the expected return
estimate and σ blended realized/implied volatility. Always labelled "estimate — not calibrated".

## Known biases

- **Survivorship bias.** Free sources mostly lack delisted stocks. The pipeline never deletes a
  ticker it has seen, and every backtested excess return is **halved** before it is shown.
- **Short opinion history.** Point-in-time analyst ratings are only available from the day
  snapshots start. Families without history are shown as information but get model weight only
  after enough live snapshots.
