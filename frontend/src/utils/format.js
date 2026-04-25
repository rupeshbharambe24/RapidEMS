// ── Severity ────────────────────────────────────────
export const SEVERITY_LABELS = {
  1: 'Critical',
  2: 'Serious',
  3: 'Moderate',
  4: 'Minor',
  5: 'Non-Emergency',
}

export const SEVERITY_COLORS = {
  1: '#ef4444',  // red
  2: '#f97316',  // orange
  3: '#f59e0b',  // amber
  4: '#06b6d4',  // cyan
  5: '#10b981',  // emerald
}

export const severityClass = (lvl) => ({
  1: 'text-sig-critical',
  2: 'text-sig-serious',
  3: 'text-sig-moderate',
  4: 'text-sig-minor',
  5: 'text-sig-minimal',
}[lvl] || 'text-slate-300')

export const severityBg = (lvl) => ({
  1: 'bg-sig-critical/15 border-sig-critical/40',
  2: 'bg-sig-serious/15 border-sig-serious/40',
  3: 'bg-sig-moderate/15 border-sig-moderate/40',
  4: 'bg-sig-minor/15 border-sig-minor/40',
  5: 'bg-sig-minimal/15 border-sig-minimal/40',
}[lvl] || 'bg-ink-700 border-line')

// ── Status ──────────────────────────────────────────
export const AMB_STATUS_COLORS = {
  available:      '#10b981',
  en_route:       '#f59e0b',
  on_scene:       '#f97316',
  transporting:   '#06b6d4',
  returning:      '#94a3b8',
  out_of_service: '#64748b',
}

export const AMB_STATUS_LABELS = {
  available: 'Available', en_route: 'En Route', on_scene: 'On Scene',
  transporting: 'Transporting', returning: 'Returning', out_of_service: 'Out of Service',
}

export const EMERGENCY_STATUS_LABELS = {
  pending: 'Pending', dispatched: 'Dispatched',
  on_scene: 'On Scene', transporting: 'Transporting',
  arrived: 'Arrived', resolved: 'Resolved', cancelled: 'Cancelled',
}

// ── Time ────────────────────────────────────────────
export function fmtSeconds(s) {
  if (s == null) return '—'
  if (s < 60) return `${Math.round(s)}s`
  const m = Math.floor(s / 60), rem = Math.round(s % 60)
  if (m < 60) return rem ? `${m}m ${rem}s` : `${m}m`
  const h = Math.floor(m / 60), mm = m % 60
  return `${h}h ${mm}m`
}

export function fmtMinutes(m) {
  if (m == null) return '—'
  if (m < 1) return `${Math.round(m * 60)}s`
  if (m < 60) return `${m.toFixed(1)}m`
  const h = Math.floor(m / 60), mm = Math.round(m % 60)
  return `${h}h ${mm}m`
}

export function fmtRelative(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const sec = Math.round((Date.now() - d.getTime()) / 1000)
  if (sec < 5) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const m = Math.round(sec / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return d.toLocaleDateString()
}

// ── Distance ────────────────────────────────────────
export function fmtKm(km) {
  if (km == null) return '—'
  if (km < 1) return `${Math.round(km * 1000)}m`
  return `${km.toFixed(1)}km`
}
