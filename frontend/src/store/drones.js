import { create } from 'zustand'
import { dronesApi } from '../api/client.js'

export const useDronesStore = create((set, get) => ({
  items: [],          // current roster
  previews: [],       // most recent scene previews (newest first, capped)
  loading: false,
  error: null,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const items = await dronesApi.list()
      set({ items, loading: false })
    } catch (e) {
      set({ error: e?.message || 'Failed to load drones', loading: false })
    }
  },

  // Live frames pushed from drone:position
  upsertPosition: ({ drone_id, registration, lat, lng, status, emergency_id }) => {
    const items = get().items
    const idx = items.findIndex(d => d.id === drone_id)
    if (idx === -1) {
      // First time we see this bird — add a thin record so the marker
      // appears even before the next /drones fetch.
      set({ items: [...items, {
        id: drone_id, registration,
        current_lat: lat, current_lng: lng,
        status: status ?? 'en_route',
        current_emergency_id: emergency_id ?? null,
        sensor_payload: [],
        base_lat: lat, base_lng: lng,
      }] })
      return
    }
    const next = items.slice()
    next[idx] = {
      ...next[idx],
      current_lat: lat, current_lng: lng,
      status: status ?? next[idx].status,
      current_emergency_id: emergency_id ?? next[idx].current_emergency_id,
    }
    set({ items: next })
  },

  setStatus: ({ drone_id, status, emergency_id }) => {
    const items = get().items.map(d =>
      d.id === drone_id
        ? { ...d, status, current_emergency_id:
              emergency_id === undefined ? d.current_emergency_id : emergency_id }
        : d)
    set({ items })
  },

  addPreview: (preview) => {
    // Cap to the most recent 20 so the map's popup history stays light.
    const previews = [preview, ...get().previews].slice(0, 20)
    set({ previews })
  },

  byId: (id) => get().items.find(d => d.id === id),
}))
