import { create } from 'zustand'
import { dispatchesApi } from '../api/client.js'

export const useDispatchesStore = create((set, get) => ({
  active: [],
  loading: false,
  error: null,

  fetchActive: async () => {
    set({ loading: true, error: null })
    try {
      const active = await dispatchesApi.active()
      set({ active, loading: false })
    } catch (e) {
      set({ error: e?.message || 'Failed', loading: false })
    }
  },

  byAmbulanceId: (amb_id) => get().active.find(d => d.ambulance_id === amb_id),
  byEmergencyId: (e_id)   => get().active.find(d => d.emergency_id === e_id),
}))
