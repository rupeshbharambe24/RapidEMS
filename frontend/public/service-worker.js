/**
 * RapidEMS Driver service worker.
 *
 * Two responsibilities:
 *  - Cache-first for the SPA shell + map tiles so the driver dashboard
 *    keeps rendering when the radio drops.
 *  - Background-sync queue for status / GPS PATCH writes that happen
 *    while offline; they replay against the live API when the SW
 *    receives a 'sync' event or the next online navigate.
 *
 * The SPA registers this from main.jsx; offline writes are mediated by
 * frontend/src/utils/offline_queue.js (IndexedDB).
 */
const SHELL_CACHE = "rapidems-shell-v1"
const TILE_CACHE = "rapidems-tiles-v1"

const SHELL_ASSETS = ["/", "/driver", "/manifest.webmanifest", "/favicon.svg"]

// ── Install: pre-cache the SPA shell ────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_ASSETS).catch(() => {})),
  )
  self.skipWaiting()
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => ![SHELL_CACHE, TILE_CACHE].includes(k))
          .map((k) => caches.delete(k)),
      ),
    ),
  )
  self.clients.claim()
})

// ── Fetch handling ──────────────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const req = event.request
  const url = new URL(req.url)

  // OSM tiles → cache-first, opportunistic refresh.
  if (url.host.endsWith(".tile.openstreetmap.org")) {
    event.respondWith(
      caches.open(TILE_CACHE).then(async (cache) => {
        const cached = await cache.match(req)
        if (cached) return cached
        try {
          const fresh = await fetch(req)
          cache.put(req, fresh.clone())
          return fresh
        } catch {
          return new Response("", { status: 504 })
        }
      }),
    )
    return
  }

  // SPA navigations → network-first, cache fallback so the driver
  // dashboard loads from cache when the radio drops mid-trip.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          caches.open(SHELL_CACHE).then((c) => c.put(req, copy))
          return res
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/driver"))),
    )
    return
  }

  // Static assets (JS/CSS chunks) — cache-first.
  if (req.method === "GET" && /\.(js|css|woff2?|svg|png)$/.test(url.pathname)) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (c) => {
        const hit = await c.match(req)
        if (hit) return hit
        const fresh = await fetch(req)
        if (fresh.ok) c.put(req, fresh.clone())
        return fresh
      }),
    )
    return
  }
})

// ── Background sync: replay queued writes ───────────────────────────────
self.addEventListener("sync", (event) => {
  if (event.tag === "rapidems-driver-queue") {
    event.waitUntil(replayQueue())
  }
})

async function replayQueue() {
  const clients = await self.clients.matchAll({ includeUncontrolled: true })
  // Hand the work to a live tab — the SPA owns the IndexedDB queue.
  for (const client of clients) {
    client.postMessage({ type: "FLUSH_OFFLINE_QUEUE" })
  }
}
