import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import { AppRoutes } from './routes'

// Hash routing (/#/stock/AAPL) works on any static host without server rewrites.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <AppRoutes />
    </HashRouter>
  </StrictMode>,
)
