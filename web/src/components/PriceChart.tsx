import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import type { ChartArrays } from '../types'

export interface ChartMarker {
  date: string
  kind: 'earnings' | 'insider' | 'signal'
  text: string
}

const MARKER_STYLE = {
  earnings: { color: '#2563eb', shape: 'circle', position: 'aboveBar' },
  insider: { color: '#059669', shape: 'arrowUp', position: 'belowBar' },
  signal: { color: '#d97706', shape: 'square', position: 'aboveBar' },
} as const

function isDark(): boolean {
  return document.documentElement.classList.contains('dark')
}

function palette(dark: boolean) {
  return {
    text: dark ? '#d4d4d8' : '#334155',
    grid: dark ? '#27272a' : '#e2e8f0',
    up: dark ? '#34d399' : '#059669',
    down: dark ? '#f87171' : '#dc2626',
    line: dark ? '#2dd4bf' : '#0f766e',
    volume: dark ? 'rgba(161,161,170,0.35)' : 'rgba(100,116,139,0.35)',
  }
}

export default function PriceChart({ chart, markers = [] }: { chart: ChartArrays; markers?: ChartMarker[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const [range, setRange] = useState<'1y' | '10y'>('1y')
  const [dark, setDark] = useState(isDark)

  useEffect(() => {
    const obs = new MutationObserver(() => setDark(isDark()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const c = palette(dark)
    const api: IChartApi = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: c.text, attributionLogo: true },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      handleScroll: { vertTouchDrag: false },
    })
    if (range === '1y' && chart.daily) {
      const d = chart.daily
      const candles = api.addSeries(CandlestickSeries, {
        upColor: c.up,
        downColor: c.down,
        wickUpColor: c.up,
        wickDownColor: c.down,
        borderVisible: false,
      })
      const bars = d.t.flatMap((t, i) => {
        const o = d.o[i], h = d.h[i], l = d.l[i], cl = d.c[i]
        return o != null && h != null && l != null && cl != null ? [{ time: t as Time, open: o, high: h, low: l, close: cl }] : []
      })
      candles.setData(bars)
      const vol = api.addSeries(HistogramSeries, { color: c.volume, priceScaleId: 'vol', priceFormat: { type: 'volume' } })
      api.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
      vol.setData(d.t.flatMap((t, i) => (d.v[i] != null ? [{ time: t as Time, value: d.v[i] as number }] : [])))
      const first = d.t[0] ?? ''
      const ms: SeriesMarker<Time>[] = markers
        .filter((m) => m.date >= first)
        .sort((a, b) => a.date.localeCompare(b.date))
        .map((m) => ({ time: m.date as Time, text: m.text, ...MARKER_STYLE[m.kind] }))
      if (ms.length) createSeriesMarkers(candles, ms)
    } else if (chart.weekly) {
      const w = chart.weekly
      const line = api.addSeries(LineSeries, { color: c.line, lineWidth: 2 })
      line.setData(w.t.map((t, i) => ({ time: t as Time, value: w.c[i] as number })))
    }
    api.timeScale().fitContent()
    return () => api.remove()
  }, [chart, range, dark, markers])

  return (
    <div>
      <div className="mb-2 flex gap-1" role="group" aria-label="Chart range">
        {(
          [
            ['1y', '1 year (daily)'],
            ['10y', '10 years (weekly)'],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-pressed={range === k}
            onClick={() => setRange(k)}
            className={`min-h-9 rounded-lg px-3 text-sm ${range === k ? 'bg-slate-900 text-white dark:bg-zinc-100 dark:text-zinc-900' : 'border border-slate-300 dark:border-zinc-600'}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div ref={ref} className="h-72 w-full sm:h-96" role="img" aria-label={`Price chart, ${range === '1y' ? 'last year, daily candles with volume' : 'last 10 years, weekly closes'}`} />
      {markers.length > 0 && range === '1y' && (
        <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
          Markers: <span className="text-blue-600">●</span> earnings · <span className="text-emerald-600">▲</span> insider buying ·{' '}
          <span className="text-amber-600">■</span> signal
        </p>
      )}
    </div>
  )
}
