import { create } from 'zustand'

const STORAGE_KEY = 'ers.auth'

const loadInitial = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return { token: null, user: null }
}

export const useAuthStore = create((set, get) => ({
  ...loadInitial(),

  login: (token, user) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }))
    set({ token, user })
  },

  logout: () => {
    localStorage.removeItem(STORAGE_KEY)
    set({ token: null, user: null })
  },

  isAuthenticated: () => !!get().token,
}))
