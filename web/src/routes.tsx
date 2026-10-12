import { Route, Routes } from 'react-router'
import { HealthProvider } from './components/HealthProvider'
import { Layout } from './components/Layout'
import About from './pages/About'
import Health from './pages/Health'
import More from './pages/More'
import NotFound from './pages/NotFound'
import { BaselineRace, Compare, Portfolio, Scorecard, Validation } from './pages/Placeholders'
import Screener from './pages/Screener'
import Stock from './pages/Stock'
import Today from './pages/Today'

/** All routes, without a router, so tests can mount them in a MemoryRouter. */
export function AppRoutes() {
  return (
    <HealthProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Today />} />
          <Route path="screener" element={<Screener />} />
          <Route path="stock/:ticker" element={<Stock />} />
          <Route path="compare" element={<Compare />} />
          <Route path="portfolio" element={<Portfolio />} />
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
