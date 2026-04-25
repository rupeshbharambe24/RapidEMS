import { create } from 'zustand'
import { emergenciesApi } from '../api/client.js'

export const useEmergenciesStore = create((set, get) => ({
  items: [],
  loading: false,
  error: null,

  fetch: async (params = {}) => {
    set({ loading: true, error: null })
    try {
      const items = await emergenciesApi.list(params)
      set({ items, loading: false })
    } catch (e) {
      set({ error: e?.message || 'Failed to load emergencies', loading: false })
    }
  },

  upsert: (e) => {
    const items = get().items
    const idx = items.findIndex(x => x.id === e.id)
    if (idx >= 0) {
      const next = [...items]
      next[idx] = { ...next[idx], ...e }
      set({ items: next })
    } else {
      set({ items: [e, ...items] })
    }
  },

  remove: (id) => set({ items: get().items.filter(e => e.id !== id) }),
  byId:   (id) => get().items.find(e => e.id === id),
}))
