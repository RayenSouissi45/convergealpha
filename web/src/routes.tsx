import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import { HealthProvider } from './components/HealthProvider'
import { Layout } from './components/Layout'
import About from './pages/About'
import Health from './pages/Health'
import More from './pages/More'
import NotFound from './pages/NotFound'
import { BaselineRace, Scorecard, Validation } from './pages/Placeholders'
import Today from './pages/Today'

// Heavy pages (table, charts) load on demand to keep the first page fast on phones.
const Screener = lazy(() => import('./pages/Screener'))
const Stock = lazy(() => import('./pages/Stock'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Compare = lazy(() => import('./pages/Compare'))

const wait = (el: React.ReactNode) => <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>{el}</Suspense>

/** All routes, without a router, so tests can mount them in a MemoryRouter. */
export function AppRoutes() {
  return (
    <HealthProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Today />} />
          <Route path="screener" element={wait(<Screener />)} />
          <Route path="stock/:ticker" element={wait(<Stock />)} />
          <Route path="compare" element={wait(<Compare />)} />
          <Route path="portfolio" element={wait(<Portfolio />)} />
          <Route path="scorecard" element={<Scorecard />} />
          <Route path="baseline-race" element={<BaselineRace />} />
          <Route path="validation" element={<Validation />} />
          <Route path="health" element={<Health />} />
          <Route path="about" element={<About />} />
          <Route path="more" element={<More />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HealthProvider>
  )
}
