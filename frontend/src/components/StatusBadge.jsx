import {
  AMB_STATUS_COLORS, AMB_STATUS_LABELS,
  EMERGENCY_STATUS_LABELS,
  SEVERITY_COLORS, SEVERITY_LABELS,
} from '../utils/format.js'

export function AmbStatusPill({ status }) {
  const color = AMB_STATUS_COLORS[status] || '#94a3b8'
  return (
    <span className="pill" style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
      <span className="pill-dot" style={{ background: color }} />
      {AMB_STATUS_LABELS[status] || status}
    </span>
  )
}

export function EmergencyStatusPill({ status }) {
  const color = status === 'pending' ? '#f59e0b'
              : status === 'resolved' ? '#10b981'
              : status === 'cancelled' ? '#64748b'
              : '#06b6d4'
  return (
    <span className="pill" style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
      <span className="pill-dot" style={{ background: color }} />
      {EMERGENCY_STATUS_LABELS[status] || status}
    </span>
  )
}

export function SeverityPill({ level, confidence }) {
  if (!level) return null
  const color = SEVERITY_COLORS[level] || '#94a3b8'
  return (
    <span className="pill" style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}>
      <span className="pill-dot" style={{ background: color }} />
      <span className="font-mono">SEV-{level}</span>
      {SEVERITY_LABELS[level]}
      {confidence != null && (
        <span className="opacity-75 font-mono">{Math.round(confidence * 100)}%</span>
      )}
    </span>
  )
}
