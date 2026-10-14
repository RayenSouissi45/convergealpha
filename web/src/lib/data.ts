import { useEffect, useState } from 'react'

// `missing` means the pipeline has not produced this file yet, which is normal early on.
export type Loadable<T> =
  | { state: 'loading' }
  | { state: 'missing' }
  | { state: 'error'; message: string }
  | { state: 'ready'; data: T }

export function dataUrl(file: string): string {
  return `${import.meta.env.BASE_URL}data/${file}`
}

export async function fetchSiteJson<T>(file: string, signal?: AbortSignal): Promise<Loadable<T>> {
  try {
    const res = await fetch(dataUrl(file), { cache: 'no-cache', signal })
    if (res.status === 404) return { state: 'missing' }
    if (!res.ok) return { state: 'error', message: `HTTP ${res.status}` }
    // Some hosts answer unknown paths with the HTML app shell instead of a 404.
    if (!(res.headers.get('content-type') ?? '').includes('json')) return { state: 'missing' }
    return { state: 'ready', data: (await res.json()) as T }
  } catch (err) {
    if (signal?.aborted) return { state: 'loading' }
    return { state: 'error', message: err instanceof Error ? err.message : String(err) }
  }
}

/** `file` null: nothing to load yet (no request is made). */
export function useSiteJson<T>(file: string | null): Loadable<T> {
  const [result, setResult] = useState<{ file: string; value: Loadable<T> } | null>(null)

  useEffect(() => {
    if (file === null) return
    const controller = new AbortController()
    void fetchSiteJson<T>(file, controller.signal).then((value) => {
      if (!controller.signal.aborted) setResult({ file, value })
    })
    return () => controller.abort()
  }, [file])

  if (file === null) return { state: 'missing' }
  return result?.file === file ? result.value : { state: 'loading' }
}

const WINDOWS_RESERVED = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
])

/** Mirrors the pipeline's stock_file_stem(): Windows cannot store CON.json, so it is CON_.json. */
export function stockFile(ticker: string): string {
  const t = ticker.toUpperCase()
  return `stocks/${WINDOWS_RESERVED.has(t) ? `${t}_` : t}.json`
}
