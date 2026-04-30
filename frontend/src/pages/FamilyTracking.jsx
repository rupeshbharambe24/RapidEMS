import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet'
import L from 'leaflet'
import {
  AlertCircle, Heart, Hospital as HospitalIcon, MapPin, Clock,
  Truck, Loader2, Activity, ShieldOff, Phone, MessageSquare, Send,
} from 'lucide-react'

import { trackingApi } from '../api/client.js'
import LangPicker from '../components/LangPicker.jsx'

// ── Markers ───────────────────────────────────────────────────────────────
const ambIcon = L.divIcon({
  className: '', iconSize: [30, 30], iconAnchor: [15, 15],
  html: '<div style="width:30px;height:30px;border-radius:50%;background:#06b6d4;border:3px solid #0a0e1a;box-shadow:0 0 0 2px #06b6d4aa,0 0 12px #06b6d4">'
        + '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#0a0e1a" stroke-width="3" style="margin:5px"><path d="M3 7h13l4 4v7H3z"/></svg></div>',
})
const incidentIcon = L.divIcon({
  className: '', iconSize: [22, 22], iconAnchor: [11, 11],
  html: '<div style="width:22px;height:22px;border-radius:50%;background:#ef4444;border:3px solid #0a0e1a;box-shadow:0 0 14px #ef4444"></div>',
})
const hospIcon = L.divIcon({
  className: '', iconSize: [22, 22], iconAnchor: [11, 11],
  html: '<div style="width:22px;height:22px;border-radius:6px;background:#10b981;border:3px solid #0a0e1a;box-shadow:0 0 12px #10b981"></div>',
})

function FlyTo({ to }) {
  const map = useMap()
  useEffect(() => { if (to) map.flyTo(to, 14, { duration: 0.6 }) }, [to])
  return null
}

export default function FamilyTracking() {
  const { token } = useParams()
  const { t } = useTranslation()
  const STATUS_LABEL = {
    dispatched:        t('track.status_dispatched'),
    en_route:          t('track.status_en_route'),
    on_scene:          t('track.status_on_scene'),
    transporting:      t('track.status_transporting'),
    arrived_hospital:  t('track.status_arrived_hospital'),
    completed:         t('track.status_completed'),
    cancelled:         t('track.status_cancelled'),
  }
  const [snap, setSnap] = useState(null)
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)

  async function load() {
    try {
      setSnap(await trackingApi.publicSnapshot(token))
      setError(null)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'Could not load this link.')
      // 410 / 404 — stop polling.
      const status = err?.response?.status
      if (status === 410 || status === 404) {
        if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
      }
    }
  }

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, 5000)
    return () => intervalRef.current && clearInterval(intervalRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (error) {
    return (
      <ErrorScreen detail={error}/>
    )
  }
  if (!snap) {
    return (
      <CenterScreen>
        <Loader2 className="w-6 h-6 animate-spin text-cyan-400"/>
        <div className="text-sm text-slate-400">{t('track.loading')}</div>
      </CenterScreen>
    )
  }

  const focus = snap.ambulance_lat && snap.ambulance_lng
              ? [snap.ambulance_lat, snap.ambulance_lng]
              : snap.incident_lat && snap.incident_lng
                ? [snap.incident_lat, snap.incident_lng]
                : [19.07, 72.87]

  const statusLabel = STATUS_LABEL[snap.dispatch_status] || 'Updating…'
  const expiresMin = Math.max(0, Math.floor((new Date(snap.expires_at) - Date.now()) / 60000))

  return (
    <div className="min-h-screen bg-ink-950 text-slate-100 flex flex-col">
      {/* Top */}
      <header className="border-b border-line/60 bg-ink-900/70 backdrop-blur px-5 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <Heart className="w-5 h-5 text-sig-critical animate-pulse"/>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
              {t('track.header')}
            </div>
            <div className="text-sm font-semibold truncate">
              {snap.patient_first_name
                ? `${snap.patient_first_name} — ${statusLabel}`
                : statusLabel}
            </div>
          </div>
          <LangPicker compact/>
          {snap.eta_minutes != null && snap.dispatch_status !== 'completed' && (
            <div className="text-right">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                {t('track.eta_label')}
              </div>
              <div className="text-2xl font-bold text-cyan-300 leading-none">
                {snap.eta_minutes.toFixed(1)}<span className="text-sm text-slate-400 ml-1">{t('common.minutes_short')}</span>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer
          center={focus} zoom={14} zoomControl={false}
          className="h-full w-full" style={{ background: '#0a0e1a' }}
          attributionControl={false}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            className="leaflet-tiles-dark"
          />
          {focus && <FlyTo to={focus}/>}

          {snap.ambulance_lat && snap.ambulance_lng && (
            <Marker position={[snap.ambulance_lat, snap.ambulance_lng]} icon={ambIcon}/>
          )}
          {snap.incident_lat && snap.incident_lng && (
            <Marker position={[snap.incident_lat, snap.incident_lng]} icon={incidentIcon}/>
          )}
          {snap.hospital_lat && snap.hospital_lng && (
            <Marker position={[snap.hospital_lat, snap.hospital_lng]} icon={hospIcon}/>
          )}
        </MapContainer>

        {/* Floating status card */}
        <div className="absolute left-3 right-3 bottom-3 sm:left-auto sm:right-3 sm:bottom-3 sm:w-[400px]
                        card p-4 backdrop-blur-md bg-ink-900/85 z-[400]">
          <div className="flex items-center gap-2 mb-2 text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
            <Activity className="w-3 h-3"/> {statusLabel}
          </div>
          {snap.ambulance_registration && (
            <div className="flex items-center gap-2 text-sm mb-1">
              <Truck className="w-4 h-4 text-cyan-400"/>
              <span className="font-mono">{snap.ambulance_registration}</span>
              {snap.ambulance_status && (
                <span className="text-[10px] font-mono text-slate-500 uppercase">
                  · {snap.ambulance_status.replace('_',' ')}
                </span>
              )}
            </div>
          )}
          {snap.hospital_name && (
            <div className="text-sm mb-2">
              <div className="flex items-center gap-2">
                <HospitalIcon className="w-4 h-4 text-emerald-400 shrink-0"/>
                <span className="truncate">{snap.hospital_name}</span>
              </div>
              {snap.hospital_address && (
                <div className="text-[11px] text-slate-400 ml-6 mt-0.5">
                  {snap.hospital_address}
                </div>
              )}
              {snap.hospital_emergency_phone && (
                <a href={`tel:${snap.hospital_emergency_phone}`}
                   className="ml-6 mt-0.5 text-[11px] font-mono text-cyan-300 inline-flex items-center gap-1">
                  <Phone className="w-3 h-3"/>{snap.hospital_emergency_phone}
                </a>
              )}
              {snap.hospital_lat && snap.hospital_lng && (
                <a href={`https://www.google.com/maps/dir/?api=1&destination=${snap.hospital_lat},${snap.hospital_lng}`}
                   target="_blank" rel="noreferrer"
                   className="ml-6 mt-0.5 text-[11px] text-cyan-300 inline-flex items-center gap-1">
                  <MapPin className="w-3 h-3"/>{t('track.directions')}
                </a>
              )}
            </div>
          )}
          {snap.severity_level && (
            <div className="text-[11px] text-slate-400 mt-2">
              {t('track.severity_label')}: <span className="font-mono">SEV-{snap.severity_level}</span>
            </div>
          )}
          {snap.last_gps_update && (
            <div className="text-[10px] font-mono text-slate-500 mt-2">
              {t('track.last_gps', { time: new Date(snap.last_gps_update).toLocaleTimeString() })}
            </div>
          )}
          <div className="text-[10px] font-mono text-slate-500 mt-2">
            {t('track.expires_in', { min: expiresMin })}
          </div>
        </div>

        {/* Notes panel — bottom-left on desktop, full-width on mobile */}
        <NotesPanel snap={snap} token={token}
                    onAdded={(n) => setSnap(s => s ? {...s, notes:[...(s.notes || []), n]} : s)}/>
      </div>
    </div>
  )
}


function NotesPanel({ snap, token, onAdded }) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(false)

  // Auto-expand once there's at least one note.
  useEffect(() => {
    if (snap.notes?.length > 0) setOpen(true)
  }, [snap.notes?.length])

  async function send(e) {
    e.preventDefault()
    if (!draft.trim()) return
    setBusy(true); setErr(null)
    try {
      const note = await trackingApi.postNote(token, {
        message: draft.trim(),
        sender_name: name.trim() || null,
      })
      onAdded(note)
      setDraft('')
    } catch (er) {
      setErr(er?.response?.data?.detail || 'Could not send.')
    } finally { setBusy(false) }
  }

  const notes = snap.notes || []
  return (
    <div className="absolute left-3 right-3 sm:left-3 sm:right-auto sm:w-[320px] bottom-3
                    card p-3 backdrop-blur-md bg-ink-900/85 z-[400]
                    sm:bottom-3 max-h-[60vh] flex flex-col">
      <button type="button" onClick={() => setOpen(o => !o)}
              className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.16em] text-slate-300">
        <MessageSquare className="w-3 h-3 text-cyan-300"/>
        {t('track.notes_title')} ({notes.length})
        <span className="text-slate-500 ml-auto">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <>
          <div className="flex-1 overflow-y-auto mt-2 space-y-1.5">
            {notes.length === 0 && (
              <div className="text-[11px] text-slate-500 italic">
                {t('track.notes_empty')}
              </div>
            )}
            {notes.map((n, i) => (
              <div key={i} className={`text-xs leading-snug px-2 py-1.5 rounded ${
                n.sender_role === 'dispatcher' ? 'bg-amber-400/10 text-amber-100' :
                n.sender_role === 'patient'    ? 'bg-emerald-400/10 text-emerald-100' :
                'bg-cyan-400/10 text-cyan-100'
              }`}>
                <div className="flex items-baseline gap-1.5 mb-0.5">
                  <span className="font-mono text-[10px] uppercase opacity-70">
                    {n.sender_role}
                  </span>
                  {n.sender_name && (
                    <span className="text-[10px] opacity-80">· {n.sender_name}</span>
                  )}
                  <span className="ml-auto text-[9px] font-mono opacity-50">
                    {new Date(n.created_at).toLocaleTimeString()}
                  </span>
                </div>
                {n.message}
              </div>
            ))}
          </div>

          <form onSubmit={send} className="mt-2 pt-2 border-t border-line/30 space-y-1.5">
            <input type="text" value={name} onChange={e => setName(e.target.value)}
                   placeholder={t('track.your_name')}
                   className="field !py-1 text-xs"/>
            <div className="flex gap-1.5">
              <input type="text" value={draft} onChange={e => setDraft(e.target.value)}
                     maxLength={400} placeholder={t('track.quick_update')}
                     className="field !py-1 text-xs flex-1"/>
              <button type="submit" disabled={busy || !draft.trim()}
                      className="btn-ghost !px-2 !py-1 text-xs disabled:opacity-40">
                {busy ? <Loader2 className="w-3 h-3 animate-spin"/> : <Send className="w-3 h-3"/>}
              </button>
            </div>
            {err && <div className="text-[10px] text-red-300">{err}</div>}
          </form>
        </>
      )}
    </div>
  )
}


function CenterScreen({ children }) {
  return (
    <div className="min-h-screen bg-ink-950 text-slate-100 grid place-items-center">
      <div className="card p-6 flex items-center gap-3">{children}</div>
    </div>
  )
}

function ErrorScreen({ detail }) {
  const { t } = useTranslation()
  const isRevoked = /revoked/i.test(detail)
  const isExpired = /expired/i.test(detail)
  return (
    <div className="min-h-screen bg-ink-950 text-slate-100 grid place-items-center px-4">
      <div className="card p-6 max-w-md text-center">
        {isRevoked
          ? <ShieldOff className="w-12 h-12 mx-auto text-amber-400 mb-3"/>
          : isExpired
            ? <Clock className="w-12 h-12 mx-auto text-amber-400 mb-3"/>
            : <AlertCircle className="w-12 h-12 mx-auto text-sig-critical mb-3"/>}
        <div className="text-lg font-bold mb-1">{t('track.unavailable')}</div>
        <div className="text-sm text-slate-400">{detail}</div>
        <div className="text-xs text-slate-500 mt-3">
          {t('track.ask_fresh')}
        </div>
        <div className="mt-4"><LangPicker/></div>
      </div>
    </div>
  )
}
