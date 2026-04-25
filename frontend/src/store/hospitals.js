import { create } from 'zustand'
import { hospitalsApi } from '../api/client.js'

export const useHospitalsStore = create((set, get) => ({
  items: [],
  loading: false,
  error: null,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const items = await hospitalsApi.list()
      set({ items, loading: false })
    } catch (e) {
      set({ error: e?.message || 'Failed to load hospitals', loading: false })
    }
  },

  updateBeds: (id, patch) => {
    const items = get().items.map(h => h.id === id ? { ...h, ...patch } : h)
    set({ items })
  },

  upsert: (h) => {
    const items = get().items
    const idx = items.findIndex(x => x.id === h.id)
    if (idx >= 0) {
      const next = [...items]; next[idx] = { ...next[idx], ...h }
      set({ items: next })
    } else set({ items: [...items, h] })
  },

  byId: (id) => get().items.find(h => h.id === id),
}))
