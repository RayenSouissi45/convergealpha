import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import { HealthProvider } from './components/HealthProvider'
import { Layout } from './components/Layout'
import Today from './pages/Today'
import NotFound from './pages/NotFound'
import More from './pages/More'
import Health from './pages/Health'
import About from './pages/About'

// Today and small pages load with the app; heavy pages (table, charts) load on demand.
const Screener = lazy(() => import('./pages/Screener'))
const Stock = lazy(() => import('./pages/Stock'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Compare = lazy(() => import('./pages/Compare'))
const Scorecard = lazy(() => import('./pages/Scorecard'))
const BaselineRace = lazy(() => import('./pages/BaselineRace'))
const Validation = lazy(() => import('./pages/Validation'))
const Picks = lazy(() => import('./pages/Picks'))
const Columns = lazy(() => import('./pages/Columns'))
const Plan = lazy(() => import('./pages/Plan'))
const Strategies = lazy(() => import('./pages/Strategies'))
const StrategyDetail = lazy(() => import('./pages/StrategyDetail'))

const wait = (el: React.ReactNode) => <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>{el}</Suspense>

/** All routes, without a router, so tests can mount them in a MemoryRouter. */
export function AppRoutes() {
  return (
    <HealthProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Today />} />
          <Route path="picks" element={wait(<Picks />)} />
          <Route path="plan" element={wait(<Plan />)} />
          <Route path="strategies" element={wait(<Strategies />)} />
          <Route path="strategies/:id" element={wait(<StrategyDetail />)} />
          <Route path="screener" element={wait(<Screener />)} />
          <Route path="columns" element={wait(<Columns />)} />
          <Route path="stock/:ticker" element={wait(<Stock />)} />
          <Route path="compare" element={wait(<Compare />)} />
          <Route path="portfolio" element={wait(<Portfolio />)} />
          <Route path="scorecard" element={wait(<Scorecard />)} />
          <Route path="baseline-race" element={wait(<BaselineRace />)} />
          <Route path="validation" element={wait(<Validation />)} />
          <Route path="health" element={<Health />} />
          <Route path="about" element={<About />} />
          <Route path="more" element={<More />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HealthProvider>
  )
}
