import { io } from 'socket.io-client'

import { useAmbulancesStore } from '../store/ambulances.js'
import { useDronesStore } from '../store/drones.js'
import { useEmergenciesStore } from '../store/emergencies.js'
import { useHospitalsStore } from '../store/hospitals.js'
import { useUiStore } from '../store/ui.js'

let socket = null

export function connectSocket() {
  if (socket && socket.connected) return socket

  // Vite proxy forwards /socket.io to backend.
  socket = io({
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
  })

  socket.on('connect', () => {
    console.log('[socket] connected', socket.id)
    useUiStore.getState().setSocketStatus('online')
  })
  socket.on('disconnect', () => {
    console.log('[socket] disconnected')
    useUiStore.getState().setSocketStatus('offline')
  })
  socket.on('connect_error', (e) => {
    console.warn('[socket] error', e.message)
    useUiStore.getState().setSocketStatus('error')
  })

  // Domain channels → mutate stores
  socket.on('ambulance:position', (msg) => {
    useAmbulancesStore.getState().updateLocation(msg.ambulance_id, msg.lat, msg.lng, msg.status)
  })
  socket.on('ambulance:status_change', (msg) => {
    useAmbulancesStore.getState().updateStatus(msg.ambulance_id, msg.status)
  })
  socket.on('emergency:created', (msg) => {
    useEmergenciesStore.getState().upsert({
      id: msg.id,
      location_lat: msg.lat,
      location_lng: msg.lng,
      status: msg.status,
      location_address: msg.address,
      chief_complaint: msg.chief_complaint,
      symptoms: msg.symptoms || [],
    })
    useUiStore.getState().toast('New emergency reported', 'critical')
  })
  socket.on('emergency:dispatched', (plan) => {
    useUiStore.getState().toast(`Dispatched ${plan.ambulance_registration} → ${plan.hospital_name}`, 'info')
  })
  socket.on('hospital:beds_updated', (msg) => {
    useHospitalsStore.getState().updateBeds(msg.hospital_id, msg)
  })

  // ── Drone reconnaissance (Phase 3.6) ──
  socket.on('drone:position', (msg) => {
    useDronesStore.getState().upsertPosition(msg)
  })
  socket.on('drone:status', (msg) => {
    useDronesStore.getState().setStatus(msg)
    if (msg.status === 'en_route' && msg.emergency_id) {
      useUiStore.getState().toast(
        `${msg.registration || 'Drone'} en-route to scene · ETA ${
          Math.round(msg.eta_seconds || 0)}s`, 'info')
    }
  })
  socket.on('drone:scene_preview', (preview) => {
    useDronesStore.getState().addPreview(preview)
    useUiStore.getState().toast(
      `Aerial: ~${preview.victim_estimate} victim(s)${
        preview.hazards?.length ? ` · ${preview.hazards.join(', ')}` : ''}`,
      preview.hazards?.length ? 'critical' : 'info')
  })

  return socket
}

export function disconnectSocket() {
  if (socket) { socket.disconnect(); socket = null }
}

export function getSocket() { return socket }
