// ConvergeAlpha service worker: works offline with the last data you opened.
// Hashed build assets: cache-first (they never change). Pages and data: network-first, falling
// back to the cached copy when offline. Bump VERSION to drop old caches.
const VERSION = 'v1'
const SHELL = `ca-shell-${VERSION}`
const DATA = `ca-data-${VERSION}`

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(['./', './index.html', './manifest.webmanifest', './favicon.svg'])))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k)))),
  )
  self.clients.claim()
})

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  } catch {
    const cached = await cache.match(request, { ignoreSearch: true })
    if (cached) return cached
    throw new Error('offline and not cached')
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(SHELL)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) cache.put(request, response.clone())
  return response
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.includes('/assets/') || url.pathname.includes('/icons/')) {
    event.respondWith(cacheFirst(event.request))
  } else if (url.pathname.includes('/data/')) {
    event.respondWith(networkFirst(event.request, DATA))
  } else if (event.request.mode === 'navigate' || url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    event.respondWith(networkFirst(event.request, SHELL))
  }
})
