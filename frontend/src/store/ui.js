import { create } from 'zustand'

let toastSeq = 0

export const useUiStore = create((set, get) => ({
  socketStatus: 'connecting',  // connecting | online | offline | error
  toasts: [],

  setSocketStatus: (s) => set({ socketStatus: s }),

  toast: (message, kind = 'info', ttl = 4500) => {
    const id = ++toastSeq
    set({ toasts: [...get().toasts, { id, message, kind }] })
    setTimeout(() => set({ toasts: get().toasts.filter(t => t.id !== id) }), ttl)
  },

  dismissToast: (id) => set({ toasts: get().toasts.filter(t => t.id !== id) }),
}))
