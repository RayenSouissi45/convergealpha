import { Link, useParams } from 'react-router'
import { Card, PageHeader } from '../components/ui'

export default function Stock() {
  const ticker = (useParams().ticker ?? '').toUpperCase()
  return (
    <>
      <PageHeader title={ticker || 'Stock'} subtitle="Stock detail" />
      <Card>
        <p className="text-sm text-slate-600 dark:text-zinc-400">
          No data for {ticker || 'this stock'} yet. Stock pages start in build phase 1 (price chart,
          returns, volatility) and gain forecasts, evidence and the position plan in later phases.
        </p>
        <Link to="/screener" className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal-700 underline dark:text-teal-400">
          Go to the screener
        </Link>
      </Card>
    </>
  )
}
