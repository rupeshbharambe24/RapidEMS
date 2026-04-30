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
  list:     (params)              => api.get('/dispatches', { params }).then(r => r.data),
  active:   ()                    => api.get('/dispatches/active').then(r => r.data),
  get:      (id)                  => api.get(`/dispatches/${id}`).then(r => r.data),
  optimize: (execute = false)     => api.post('/dispatches/optimize',
                                              null, { params: { execute } }).then(r => r.data),
}

// ─────────── AI inference ───────────
export const aiApi = {
  triage:   (payload) => api.post('/ai/triage',  payload).then(r => r.data),
  eta:      (payload) => api.post('/ai/eta',     payload).then(r => r.data),
  traffic:  (payload) => api.post('/ai/traffic', payload).then(r => r.data),
  hotspot:  (zone_id) => api.get('/ai/hotspots', { params: { zone_id } }).then(r => r.data),
  extract:  (transcript, language_hint) =>
    api.post('/ai/extract', { transcript, language_hint }).then(r => r.data),
  extractMultimodal: (payload) =>
    api.post('/ai/extract-multimodal', payload).then(r => r.data),
  explain:  (payload) => api.post('/ai/explain', payload).then(r => r.data),
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

// ─────────── Public transparency dashboard (no auth) ───────────
// Built with raw axios so the JWT interceptor doesn't fire for guest visitors.
const _publicAxios = axios.create({ baseURL: '/' })
export const publicApi = {
  heartbeat: ()        => _publicAxios.get('/public-api/heartbeat').then(r => r.data),
  city:      ()        => _publicAxios.get('/public-api/city').then(r => r.data),
  zones:     (n=12)    => _publicAxios.get('/public-api/zones',
                                           { params: { n_zones: n } }).then(r => r.data),
  hospitals: ()        => _publicAxios.get('/public-api/hospitals').then(r => r.data),
}

// ─────────── Family tracking ───────────
// Note: backend mounts under /track-api so the SPA route /track/:token is free.
// publicSnapshot + postNote are no-auth: send via the bare _publicAxios so
// the JWT interceptor doesn't fire when a guest opens the link.
export const trackingApi = {
  publicSnapshot: (token)        => _publicAxios.get(`/track-api/${encodeURIComponent(token)}`).then(r => r.data),
  postNote:       (token, payload) => _publicAxios.post(`/track-api/${encodeURIComponent(token)}/notes`, payload).then(r => r.data),
  createLink:     (payload)      => api.post('/track-api/links', payload).then(r => r.data),
  listMine:       ()             => api.get('/track-api/links').then(r => r.data),
  revoke:         (id)           => api.post(`/track-api/links/${id}/revoke`).then(r => r.data),
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

// ─────────── Admin ───────────
export const adminApi = {
  overview:        ()                  => api.get('/admin/overview').then(r => r.data),
  listUsers:       (params)            => api.get('/admin/users', { params }).then(r => r.data),
  createUser:      (payload)           => api.post('/admin/users', payload).then(r => r.data),
  updateUser:      (id, payload)       => api.patch(`/admin/users/${id}`, payload).then(r => r.data),
  deactivateUser:  (id)                => api.delete(`/admin/users/${id}`).then(r => r.data),
  auditLog:        (params)            => api.get('/admin/audit-log', { params }).then(r => r.data),
  assignAmbulance: (ambId, userId)     => api.patch(`/admin/ambulances/${ambId}/assign`,
                                          { user_id: userId }).then(r => r.data),

  // Chaos lab (Phase 3.10)
  chaosState:      ()                  => api.get('/admin/chaos').then(r => r.data),
  chaosInject:     (payload)           => api.post('/admin/chaos/inject', payload).then(r => r.data),
  chaosClear:      (scenario)          => api.post('/admin/chaos/clear',
                                          null, { params: scenario ? { scenario } : {} }).then(r => r.data),

  // Cinematic demo + replay (Phase 3.1)
  demoScenarios:   ()                  => api.get('/admin/demo/scenarios').then(r => r.data),
  demoStart:       (payload)           => api.post('/admin/demo/start', payload).then(r => r.data),
  demoStatus:      ()                  => api.get('/admin/demo/status').then(r => r.data),
  demoStop:        ()                  => api.post('/admin/demo/stop').then(r => r.data),
  replayList:      ()                  => api.get('/admin/replay').then(r => r.data),
  replayStart:     (payload)           => api.post('/admin/replay/start', payload).then(r => r.data),
  replayStatus:    ()                  => api.get('/admin/replay/status').then(r => r.data),
}

// ─────────── Copilot ───────────
export const copilotApi = {
  ask: (query, context) =>
    api.post('/copilot/ask', { query, context }).then(r => r.data),
}

// ─────────── Drones (Phase 3.6) ───────────
export const dronesApi = {
  list:     ()                  => api.get('/drones').then(r => r.data),
  active:   ()                  => api.get('/drones/active').then(r => r.data),
  dispatch: (emergency_id)      => api.post('/drones/dispatch',
                                    { emergency_id }).then(r => r.data),
}

// ─────────── Wearable telemetry ───────────
export const telemetryApi = {
  ingest: (readings)         => api.post('/telemetry/batch', { readings }).then(r => r.data),
  list:   (params)           => api.get('/telemetry/me', { params }).then(r => r.data),
  latest: ()                 => api.get('/telemetry/me/latest').then(r => r.data),
}

// ─────────── Notifications ───────────
export const notificationsApi = {
  capabilities: ()           => api.get('/notifications/capabilities').then(r => r.data),
  list:         ()           => api.get('/notifications').then(r => r.data),
  add:          (payload)    => api.post('/notifications', payload).then(r => r.data),
  update:       (id, payload)=> api.patch(`/notifications/${id}`, payload).then(r => r.data),
  test:         (id)         => api.post(`/notifications/${id}/test`).then(r => r.data),
  remove:       (id)         => api.delete(`/notifications/${id}`).then(r => r.data),
}

// ─────────── Hospital portal ───────────
export const hospitalPortalApi = {
  me:           ()              => api.get('/hospital/me').then(r => r.data),
  claim:        (hid)           => api.post(`/hospital/claim/${hid}`).then(r => r.data),
  release:      ()              => api.post('/hospital/release').then(r => r.data),
  listAlerts:   (only_open=true)=> api.get('/hospital/alerts',
                                          { params: { only_open } }).then(r => r.data),
  acknowledge:  (id)            => api.post(`/hospital/alerts/${id}/acknowledge`).then(r => r.data),
  accept:       (id)            => api.post(`/hospital/alerts/${id}/accept`).then(r => r.data),
  divert:       (id, set_hospital=true) =>
                                  api.post(`/hospital/alerts/${id}/divert`,
                                          { set_hospital_diversion: set_hospital }).then(r => r.data),
  regenerateBriefing: (id)      => api.post(`/hospital/alerts/${id}/briefing/regenerate`).then(r => r.data),
  updateBeds:   (payload)       => api.patch('/hospital/me/beds', payload).then(r => r.data),
}

// ─────────── Health ───────────
export const healthApi = () => api.get('/health').then(r => r.data)

export default api
