import { create } from 'zustand'
import { ambulancesApi } from '../api/client.js'

export const useAmbulancesStore = create((set, get) => ({
  items: [],
  loading: false,
  error: null,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const items = await ambulancesApi.list()
      set({ items, loading: false })
    } catch (e) {
      set({ error: e?.message || 'Failed to load ambulances', loading: false })
    }
  },

  // Called from Socket.IO handler
  updateLocation: (id, lat, lng, status) => {
    const items = get().items.map(a =>
      a.id === id
        ? { ...a, current_lat: lat, current_lng: lng,
            status: status ?? a.status,
            last_gps_update: new Date().toISOString() }
        : a)
    set({ items })
  },

  updateStatus: (id, status) => {
    const items = get().items.map(a => a.id === id ? { ...a, status } : a)
    set({ items })
  },

  byId: (id) => get().items.find(a => a.id === id),
}))
