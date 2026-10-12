import { PageHeader, Planned } from '../components/ui'

export function Scorecard() {
  return (
    <>
      <PageHeader title="Scorecard" subtitle="Predicted vs what actually happened." />
      <Planned title="Live track record" phase={6}>
        <p>
          For each label and horizon: reliability chart, hit rate together with payoff ratio and
          expected value, Brier score, and live vs backtest. Built from an append-only,
          hash-chained ledger written before outcomes are known.
        </p>
      </Planned>
    </>
  )
}

export function BaselineRace() {
  return (
    <>
      <PageHeader title="Baseline race" subtitle="Does the app beat simple alternatives?" />
      <Planned title="App vs baselines" phase={6}>
        <p>
          The app against the S&P 500, momentum-only, revisions-only, an equal-weight family average
          and any third-party lists, all under the same rules and costs.
        </p>
      </Planned>
    </>
  )
}

export function Validation() {
  return (
    <>
      <PageHeader title="Validation" subtitle="The test every probability must pass." />
      <Planned title="Validation report" phase={5}>
        <p>
          Walk-forward backtest with a holdout run once, results vs every baseline, calibration,
          drawdown, costs at 2×, deflated Sharpe ratio and probability of overfitting — failures
          included.
        </p>
        <p>
          Until a horizon or label passes, every probability for it carries the RESEARCH MODE
          badge.
        </p>
      </Planned>
    </>
  )
}
