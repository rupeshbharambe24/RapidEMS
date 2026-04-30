import L from 'leaflet'
import { AMB_STATUS_COLORS, SEVERITY_COLORS } from './format.js'

// Default Leaflet marker images break with bundlers — we suppress them.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'data:image/svg+xml;base64,PHN2Zy8+',
  iconUrl:       'data:image/svg+xml;base64,PHN2Zy8+',
  shadowUrl:     'data:image/svg+xml;base64,PHN2Zy8+',
})

// ── Ambulance icon ─────────────────────────────────────
export function ambulanceIcon(status = 'available') {
  const color = AMB_STATUS_COLORS[status] || '#94a3b8'
  return L.divIcon({
    className: '',
    iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -14],
    html: `
      <div class="amb-marker" style="background:${color}; border:2px solid #0a0e1a">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10 17h4V5H2v12h3"/><path d="M14 17h1l3-5h4v5h2"/>
          <circle cx="7.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>
          <path d="M6 11h2m-1-1v2"/>
        </svg>
      </div>`,
  })
}

// ── Hospital icon ─────────────────────────────────────
export function hospitalIcon(beds = 0) {
  // ring color reflects available bed count
  const ring = beds > 30 ? '#10b981' : beds > 10 ? '#f59e0b' : '#ef4444'
  return L.divIcon({
    className: '',
    iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -16],
    html: `
      <div class="hosp-marker" style="background:#10162a; border:2px solid ${ring}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${ring}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 6v12M6 12h12"/>
        </svg>
      </div>`,
  })
}

// ── Drone icon (Phase 3.6) ────────────────────────────
const DRONE_STATUS_COLORS = {
  available: '#475569',   // depot, dim
  en_route:  '#06b6d4',   // cyan, flying out
  on_scene:  '#a855f7',   // purple, observing
  returning: '#0891b2',   // muted cyan, heading home
}

export function droneIcon(status = 'available') {
  const color = DRONE_STATUS_COLORS[status] || '#94a3b8'
  const pulse = status === 'en_route' || status === 'on_scene'
  return L.divIcon({
    className: '',
    iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -14],
    html: `
      <div style="position:relative">
        ${pulse ? `<div class="drone-pulse" style="background:${color}55"></div>` : ''}
        <div class="drone-marker" style="background:${color}; border:2px solid #0a0e1a">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/>
            <circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>
            <path d="M8 6h8M8 18h8M6 8v8M18 8v8"/>
            <rect x="10" y="10" width="4" height="4" rx="0.5"/>
          </svg>
        </div>
      </div>`,
  })
}

// ── Emergency icon (pulsing) ──────────────────────────
export function emergencyIcon(severity = 3) {
  const color = SEVERITY_COLORS[severity] || '#94a3b8'
  return L.divIcon({
    className: '',
    iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -14],
    html: `
      <div style="position:relative">
        <div class="emerg-pulse" style="background:${color}55"></div>
        <div class="emerg-marker" style="background:${color}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
            <path d="M12 9v4"/><path d="M12 17h.01"/>
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          </svg>
        </div>
      </div>`,
  })
}
