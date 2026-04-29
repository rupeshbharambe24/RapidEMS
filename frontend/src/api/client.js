import axios from 'axios'
import { useAuthStore } from '../store/auth.js'

// Vite proxy forwards /auth /emergencies /ambulances etc. to backend.
const api = axios.create({ baseURL: '/' })

// ── JWT injector ──
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Auto-logout on 401 ──
api.interceptors.response.use(
  r => r,
  err => {
    if (err?.response?.status === 401) {
      // token invalid/expired
      useAuthStore.getState().logout()
    }
    return Promise.reject(err)
  },
)

// ─────────── Auth ───────────
export const authApi = {
  login:    (username, password) => api.post('/auth/login',    { username, password }).then(r => r.data),
  register: (payload)            => api.post('/auth/register', payload).then(r => r.data),
  me:       ()                   => api.get('/auth/me').then(r => r.data),
}

// ─────────── Emergencies ───────────
export const emergenciesApi = {
  list:     (params)         => api.get('/emergencies',     { params }).then(r => r.data),
  get:      (id)             => api.get(`/emergencies/${id}`).then(r => r.data),
  create:   (payload)        => api.post('/emergencies', payload).then(r => r.data),
  update:   (id, payload)    => api.patch(`/emergencies/${id}`, payload).then(r => r.data),
  dispatch: (id)             => api.post(`/emergencies/${id}/dispatch`).then(r => r.data),
}

// ─────────── Ambulances ───────────
export const ambulancesApi = {
  list:           (params)        => api.get('/ambulances', { params }).then(r => r.data),
  get:            (id)            => api.get(`/ambulances/${id}`).then(r => r.data),
  updateLocation: (id, lat, lng)  => api.patch(`/ambulances/${id}/location`,
                                                { current_lat: lat, current_lng: lng }).then(r => r.data),
  updateStatus:   (id, status)    => api.patch(`/ambulances/${id}/status`,
                                                { status }).then(r => r.data),
}

// ─────────── Hospitals ───────────
export const hospitalsApi = {
  list:        ()           => api.get('/hospitals').then(r => r.data),
  get:         (id)         => api.get(`/hospitals/${id}`).then(r => r.data),
  updateBeds:  (id, payload)=> api.patch(`/hospitals/${id}/beds`, payload).then(r => r.data),
}

// ─────────── Dispatches ───────────
export const dispatchesApi = {
  list:    (params) => api.get('/dispatches', { params }).then(r => r.data),
  active:  ()       => api.get('/dispatches/active').then(r => r.data),
  get:     (id)     => api.get(`/dispatches/${id}`).then(r => r.data),
}

// ─────────── AI inference ───────────
export const aiApi = {
  triage:   (payload) => api.post('/ai/triage',  payload).then(r => r.data),
  eta:      (payload) => api.post('/ai/eta',     payload).then(r => r.data),
  traffic:  (payload) => api.post('/ai/traffic', payload).then(r => r.data),
  hotspot:  (zone_id) => api.get('/ai/hotspots', { params: { zone_id } }).then(r => r.data),
  extract:  (transcript, language_hint) =>
    api.post('/ai/extract', { transcript, language_hint }).then(r => r.data),
}

// ─────────── Analytics ───────────
export const analyticsApi = {
  kpis:     ()                  => api.get('/analytics/kpis').then(r => r.data),
  hotspots: (n_zones=12)        => api.get('/analytics/hotspots', { params: { n_zones } }).then(r => r.data),
}

// ─────────── Patient ───────────
export const patientApi = {
  myProfile:        ()         => api.get('/patient/me').then(r => r.data),
  createProfile:    (payload)  => api.post('/patient/me', payload).then(r => r.data),
  updateProfile:    (payload)  => api.patch('/patient/me', payload).then(r => r.data),
  listRecords:      ()         => api.get('/patient/records').then(r => r.data),
  uploadRecord:     (file, recordType, description) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('record_type', recordType)
    fd.append('description', description || '')
    return api.post('/patient/records', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  deleteRecord:     (id)       => api.delete(`/patient/records/${id}`).then(r => r.data),
  downloadRecordUrl:(id)       => `/patient/records/${id}/download`,
  raiseSos:         (payload)  => api.post('/patient/sos', payload).then(r => r.data),
  activeEmergency:  ()         => api.get('/patient/active-emergency').then(r => r.data),
}

// ─────────── Routing ───────────
export const routingApi = {
  preview: (from_lat, from_lng, to_lat, to_lng) =>
    api.get('/routing/preview',
      { params: { from_lat, from_lng, to_lat, to_lng } }).then(r => r.data),
}

// ─────────── Driver / paramedic ───────────
export const driverApi = {
  me:        ()              => api.get('/driver/me').then(r => r.data),
  claim:     (ambId)         => api.post(`/driver/claim/${ambId}`).then(r => r.data),
  release:   ()              => api.post('/driver/release').then(r => r.data),
  advance:   (target = null) => api.patch('/driver/status', { target }).then(r => r.data),
  pushGps:   (lat, lng)      => api.patch('/driver/location', { lat, lng }).then(r => r.data),
}

// ─────────── Health ───────────
export const healthApi = () => api.get('/health').then(r => r.data)

export default api
