/**
 * Offline write queue for the paramedic driver dashboard.
 *
 * The driver app issues two kinds of writes during a trip:
 *   PATCH /driver/location   GPS push, every few seconds
 *   PATCH /driver/status     manual state advance (en_route → on_scene → …)
 *
 * Both are idempotent enough that re-sending stale entries on reconnect
 * is fine: location updates collapse to the latest one server-side, and
 * status transitions are gated by the engine's state machine.
 *
 * IndexedDB is chosen over localStorage because:
 *   - Survives across tabs and PWA installs.
 *   - Plays well with Background Sync (the SW pings the live tab via
 *     postMessage when sync fires; the tab walks the store and replays).
 *
 * Public API:
 *   enqueue(method, url, body, headers)
 *   flush(api)         — drain the queue against `api` (an axios instance)
 *   pending()          — returns the current queue length
 *   onFlush(callback)  — fired when the SW asks for a flush
 */
const DB_NAME = "rapidems-driver"
const STORE = "queue"
const DB_VERSION = 1

function _openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function _withStore(mode, fn) {
  const db = await _openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode)
    const store = tx.objectStore(STORE)
    const result = fn(store)
    tx.oncomplete = () => resolve(result)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

export async function enqueue(method, url, body, headers) {
  const item = {
    method, url, body: body ?? null, headers: headers ?? null,
    queued_at: new Date().toISOString(),
  }
  return _withStore("readwrite", (s) => s.add(item))
}

export async function pending() {
  return _withStore("readonly", (s) => new Promise((resolve, reject) => {
    const req = s.count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  }))
}

export async function flush(api) {
  // Walk in id order; on any 5xx or network failure, stop and leave the
  // remaining rows for the next attempt.
  const db = await _openDb()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, "readwrite")
    const store = tx.objectStore(STORE)
    const cursorReq = store.openCursor()
    let sent = 0
    let failed = 0

    cursorReq.onsuccess = async (e) => {
      const cursor = e.target.result
      if (!cursor) {
        resolve({ sent, failed })
        return
      }
      const item = cursor.value
      try {
        await api.request({
          method: item.method, url: item.url,
          data: item.body, headers: item.headers || undefined,
        })
        sent++
        cursor.delete()
        cursor.continue()
      } catch (err) {
        const status = err?.response?.status
        if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
          // Permanent client-side error — drop so we don't retry forever.
          cursor.delete()
          failed++
          cursor.continue()
        } else {
          // Transient — leave it and stop draining.
          failed++
          resolve({ sent, failed })
        }
      }
    }
  })
}

const _flushListeners = new Set()
export function onFlush(cb) {
  _flushListeners.add(cb)
  return () => _flushListeners.delete(cb)
}

// Listen for the service-worker FLUSH_OFFLINE_QUEUE message.
if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
  navigator.serviceWorker?.addEventListener?.("message", (e) => {
    if (e.data?.type === "FLUSH_OFFLINE_QUEUE") {
      _flushListeners.forEach((cb) => cb())
    }
  })
}
