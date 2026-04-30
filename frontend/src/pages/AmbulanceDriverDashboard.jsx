import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MapContainer, TileLayer, Marker, Polyline, useMap,
} from 'react-leaflet'
import {
  Truck, Phone, MapPin, ChevronRight, AlertCircle, Loader2, LogOut,
  Heart, Hospital as HospitalIcon, Activity, CheckCircle2, RotateCcw,
  AlertTriangle, FileWarning, WifiOff, CloudOff,
} from 'lucide-react'
import L from 'leaflet'

import { driverApi, ambulancesApi } from '../api/client.js'
import api from '../api/client.js'
import { enqueue, flush, onFlush, pending } from '../utils/offline_queue.js'
import { useAuthStore } from '../store/auth.js'
import { useUiStore } from '../store/ui.js'

// ── Status state machine (mirror of backend) ──────────────────────────────
const NEXT_LABEL = {
  dispatched: 'Acknowledge — En Route',
  en_route: 'On Scene',
  on_scene: 'Transporting',
  transporting: 'At Hospital',
  arrived_hospital: 'Mark Available',
}

const STATUS_TINT = {
  dispatched: 'border-cyan-400/40 text-cyan-200',
  en_route: 'border-amber-400/50 text-amber-200',
  on_scene: 'border-orange-400/50 text-orange-200',
  transporting: 'border-sig-critical/50 text-red-200',
  arrived_hospital: 'border-emerald-400/50 text-emerald-200',
  completed: 'border-line/40 text-slate-400',
}

// ── Tiny leaflet markers ──────────────────────────────────────────────────
const ambIcon = L.divIcon({
  className: '', iconSize: [28, 28], iconAnchor: [14, 14],
  html: '<div style="width:28px;height:28px;border-radius:50%;background:#06b6d4;border:3px solid #0a0e1a;box-shadow:0 0 0 2px #06b6d4aa,0 0 12px #06b6d4">'
        + '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#0a0e1a" stroke-width="3" style="margin:4px"><path d="M3 7h13l4 4v7H3z"/></svg></div>',
})
const sceneIcon = L.divIcon({
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

export default function AmbulanceDriverDashboard() {
  const nav = useNavigate()
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const toast = useUiStore(s => s.toast)

  const [me, setMe] = useState(null)
  const [fleet, setFleet] = useState([])
  const [busy, setBusy] = useState(false)
  const [advancing, setAdvancing] = useState(false)
  const [queueDepth, setQueueDepth] = useState(0)
  const [online, setOnline] = useState(typeof navigator !== 'undefined'
                                       ? navigator.onLine : true)
  const watchIdRef = useRef(null)

  // ── Initial load + claim picker if no ambulance yet ─────────────────────
  useEffect(() => {
    (async () => {
      try {
        setMe(await driverApi.me())
      } catch (err) {
        if (err?.response?.status === 409) {
          // No ambulance claimed yet; load fleet for the picker.
          try { setFleet(await ambulancesApi.list()) } catch {}
        } else {
          toast(err?.response?.data?.detail || 'Driver load failed', 'critical')
        }
      }
    })()
  }, [])

  // Re-poll active assignment every 5s (catches new dispatches).
  useEffect(() => {
    if (!me?.ambulance) return
    const t = setInterval(async () => {
      try { setMe(await driverApi.me()) } catch {}
    }, 5000)
    return () => clearInterval(t)
  }, [me?.ambulance?.id])

  // ── Live GPS push while signed in to a unit ─────────────────────────────
  useEffect(() => {
    if (!me?.ambulance || !navigator.geolocation) return
    if (watchIdRef.current) return  // already watching
    watchIdRef.current = navigator.geolocation.watchPosition(
      async pos => {
        const lat = pos.coords.latitude, lng = pos.coords.longitude
        try {
          await driverApi.pushGps(lat, lng)
        } catch {
          // Network drop or server unreachable — queue for replay.
          await enqueue('PATCH', '/driver/location', { lat, lng })
          setQueueDepth(await pending())
        }
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 8000, timeout: 10000 },
    )
    return () => {
      if (watchIdRef.current != null) {
        navigator.geolocation.clearWatch(watchIdRef.current)
        watchIdRef.current = null
      }
    }
  }, [me?.ambulance?.id])

  // ── Online / offline + queue replay ────────────────────────────────────
  useEffect(() => {
    async function refreshDepth() { setQueueDepth(await pending()) }
    refreshDepth()

    async function doFlush() {
      const r = await flush(api)
      const dep = await pending()
      setQueueDepth(dep)
      if (r.sent > 0 && dep === 0) {
        toast(`Synced ${r.sent} queued update${r.sent === 1 ? '' : 's'}.`, 'success')
      }
    }
    function onOnline() { setOnline(true); doFlush() }
    function onOffline() { setOnline(false) }
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    const off = onFlush(doFlush)   // SW background-sync handoff

    // Best-effort flush on mount in case there's leftover queue from a
    // previous session.
    if (navigator.onLine) doFlush()

    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      off?.()
    }
  }, [])

  async function claim(ambId) {
    setBusy(true)
    try {
      await driverApi.claim(ambId)
      setMe(await driverApi.me())
      toast('Ambulance claimed', 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Claim failed', 'critical')
    } finally { setBusy(false) }
  }

  async function advance() {
    if (!me?.active_dispatch) return
    setAdvancing(true)
    try {
      await driverApi.advance()
      setMe(await driverApi.me())
    } catch (err) {
      // Network error — queue and let the user keep moving. Server-side
      // 4xx responses (legal-transition violations etc.) are still surfaced.
      const offlineLike = !err?.response || err?.code === 'ERR_NETWORK'
      if (offlineLike) {
        await enqueue('PATCH', '/driver/status', { target: null })
        setQueueDepth(await pending())
        toast('No signal — status update queued, will sync.', 'info')
      } else {
        toast(err?.response?.data?.detail || 'Status advance failed', 'critical')
      }
    } finally { setAdvancing(false) }
  }

  async function release() {
    if (!confirm('Release this ambulance? You will be unassigned.')) return
    try {
      await driverApi.release()
      setMe(null)
      setFleet(await ambulancesApi.list())
      toast('Released', 'info')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Release failed', 'critical')
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  if (!me) return (
    <ClaimScreen fleet={fleet} onClaim={claim} busy={busy}
                 user={user} onLogout={() => { logout(); nav('/login') }}/>
  )

  const amb = me.ambulance
  const d = me.active_dispatch
  const e = me.emergency
  const h = me.hospital
  const status = d?.status
  const phase = status === 'dispatched' || status === 'en_route' ? 'to_scene'
              : (status === 'on_scene' || status === 'transporting' || status === 'arrived_hospital') ? 'to_hospital'
              : null
  const activeLeg = phase === 'to_scene' ? me.leg_to_scene
                  : phase === 'to_hospital' ? me.leg_to_hospital
                  : null
  const focusTarget = phase === 'to_scene' && e ? [e.location_lat, e.location_lng]
                    : phase === 'to_hospital' && h ? [h.lat, h.lng]
                    : amb.current_lat && amb.current_lng ? [amb.current_lat, amb.current_lng]
                    : [19.07, 72.87]

  return (
    <div className="h-screen w-screen flex flex-col bg-ink-950 text-slate-100 overflow-hidden">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <header className="border-b border-line/60 bg-ink-900/60 backdrop-blur px-4 py-3 flex items-center gap-3">
        <Truck className="w-5 h-5 text-cyan-400"/>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
            unit
          </div>
          <div className="font-mono text-sm truncate">
            {amb.registration_number} · {amb.ambulance_type.toUpperCase()}
          </div>
        </div>
        {!online && (
          <div className="flex items-center gap-1 px-2 py-1 rounded border border-amber-400/50
                          text-amber-300 text-[10px] font-mono uppercase tracking-wider">
            <WifiOff className="w-3 h-3"/>offline
          </div>
        )}
        {queueDepth > 0 && (
          <div className="flex items-center gap-1 px-2 py-1 rounded border border-cyan-400/40
                          text-cyan-300 text-[10px] font-mono uppercase tracking-wider"
               title="Queued updates that will sync when the radio comes back">
            <CloudOff className="w-3 h-3"/>{queueDepth}
          </div>
        )}
        {status && (
          <div className={`px-2 py-1 rounded border text-[10px] font-mono uppercase tracking-wider ${STATUS_TINT[status] || ''}`}>
            {status.replace('_',' ')}
          </div>
        )}
        <button onClick={release} className="btn-ghost text-xs px-2 py-1.5"
                title="Release ambulance">
          <RotateCcw className="w-3.5 h-3.5"/>
        </button>
        <button onClick={() => { logout(); nav('/login') }}
                className="btn-ghost text-xs px-2 py-1.5">
          <LogOut className="w-3.5 h-3.5"/>
        </button>
      </header>

      {/* ── Map ────────────────────────────────────────────────────────── */}
      <div className="flex-1 relative">
        <MapContainer
          center={focusTarget} zoom={14} zoomControl={false}
          className="h-full w-full" style={{ background: '#0a0e1a' }}
          attributionControl={false}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            className="leaflet-tiles-dark"
          />
          {focusTarget && <FlyTo to={focusTarget}/>}

          {amb.current_lat && amb.current_lng && (
            <Marker position={[amb.current_lat, amb.current_lng]} icon={ambIcon}/>
          )}
          {e && <Marker position={[e.location_lat, e.location_lng]} icon={sceneIcon}/>}
          {h && <Marker position={[h.lat, h.lng]} icon={hospIcon}/>}

          {phase === 'to_scene' && me.leg_to_scene?.polyline?.length > 1 && (
            <Polyline
              positions={me.leg_to_scene.polyline.map(([lng, lat]) => [lat, lng])}
              pathOptions={{ color: '#ef4444', weight: 4, opacity: 0.85 }}
            />
          )}
          {phase === 'to_hospital' && me.leg_to_hospital?.polyline?.length > 1 && (
            <Polyline
              positions={me.leg_to_hospital.polyline.map(([lng, lat]) => [lat, lng])}
              pathOptions={{ color: '#10b981', weight: 4, opacity: 0.85 }}
            />
          )}
        </MapContainer>

        {/* ── Floating dispatch card ─────────────────────────────────── */}
        {d ? (
          <div className="absolute left-3 right-3 bottom-3 sm:left-auto sm:right-3 sm:bottom-3 sm:w-[420px]
                          card p-4 backdrop-blur-md bg-ink-900/85 z-[400]">
            <div className="flex items-center gap-2 mb-2 text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
              <Activity className="w-3 h-3"/> dispatch #{d.id}
              {phase === 'to_scene' && <span className="text-amber-300">· heading to scene</span>}
              {phase === 'to_hospital' && <span className="text-red-300">· transport to hospital</span>}
            </div>

            {/* Patient summary */}
            {e && (
              <div className="flex items-start gap-2 mb-2">
                <Heart className="w-4 h-4 text-sig-critical mt-0.5 shrink-0"/>
                <div className="text-sm">
                  <div className="font-semibold">
                    {e.patient_name || 'Patient'}{e.patient_age ? `, ${e.patient_age}` : ''}
                    {e.patient_gender ? ` (${e.patient_gender})` : ''}
                  </div>
                  <div className="text-slate-400 text-xs">
                    SEV-{e.predicted_severity ?? '?'} ·
                    {' '}{(e.symptoms || []).slice(0, 3).map(s => s.replaceAll('_',' ')).join(', ') || '—'}
                  </div>
                  {e.chief_complaint && (
                    <div className="text-slate-500 text-xs italic mt-0.5 line-clamp-2">
                      "{e.chief_complaint}"
                    </div>
                  )}
                  {e.phone && (
                    <a href={`tel:${e.phone}`}
                       className="text-cyan-300 text-xs font-mono inline-flex items-center gap-1 mt-1">
                      <Phone className="w-3 h-3"/> {e.phone}
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Hospital */}
            {h && (
              <div className="flex items-start gap-2 mb-2">
                <HospitalIcon className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0"/>
                <div className="text-sm">
                  <div className="font-semibold">{h.name}</div>
                  <div className="text-slate-500 text-xs">
                    {h.specialties?.slice(0,3).join(' · ')}
                  </div>
                </div>
              </div>
            )}

            {/* Clinical context — blood group + allergies + chronic conditions */}
            {(me.patient_blood_group || me.patient_allergies
              || me.patient_chronic_conditions || me.patient_current_medications) && (
              <div className="mb-2 px-2 py-1.5 rounded bg-ink-700/40 text-[11px] space-y-0.5">
                {me.patient_blood_group && (
                  <div className="flex gap-2"><span className="text-slate-500 w-16 shrink-0">blood</span>
                    <span className="font-mono">{me.patient_blood_group}</span></div>
                )}
                {me.patient_allergies && (
                  <div className="flex gap-2"><span className="text-amber-400 w-16 shrink-0">allergy</span>
                    <span className="text-amber-200">{me.patient_allergies}</span></div>
                )}
                {me.patient_chronic_conditions && (
                  <div className="flex gap-2"><span className="text-slate-500 w-16 shrink-0">chronic</span>
                    <span>{me.patient_chronic_conditions}</span></div>
                )}
                {me.patient_current_medications && (
                  <div className="flex gap-2"><span className="text-slate-500 w-16 shrink-0">meds</span>
                    <span className="text-slate-300">{me.patient_current_medications}</span></div>
                )}
              </div>
            )}

            {/* Drug interaction warnings */}
            {me.drug_warnings?.length > 0 && (
              <div className="mb-3 p-2 rounded border border-amber-400/40 bg-amber-400/5">
                <div className="flex items-center gap-1.5 mb-1 text-[10px] font-mono uppercase tracking-wider text-amber-200">
                  <FileWarning className="w-3 h-3"/>drug-interaction warnings ({me.drug_warnings.length})
                </div>
                <ul className="space-y-1">
                  {me.drug_warnings.map((w, i) => (
                    <li key={i} className="text-[11px] flex gap-1.5 leading-snug">
                      <AlertTriangle className={`w-3 h-3 mt-0.5 shrink-0 ${
                        w.tier === 'major' ? 'text-sig-critical' : 'text-amber-300'}`}/>
                      <span className={w.tier === 'major' ? 'text-red-200' : 'text-amber-100'}>
                        {w.note}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Active leg */}
            {activeLeg && (
              <div className="flex items-center justify-between gap-3 mb-3 px-2 py-1.5 rounded bg-ink-700/40">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  {phase === 'to_scene' ? 'to scene' : 'to hospital'}
                </div>
                <div className="text-sm font-mono">
                  {activeLeg.minutes}m · {activeLeg.km}km
                </div>
                <div className="text-[10px] font-mono text-slate-500">
                  {activeLeg.provider}
                </div>
              </div>
            )}

            {/* Next action */}
            {NEXT_LABEL[status] ? (
              <button
                onClick={advance}
                disabled={advancing}
                className="w-full py-3 rounded bg-sig-critical hover:bg-sig-critical/90 text-white font-bold disabled:opacity-40"
              >
                {advancing
                  ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin"/>updating…</span>
                  : <span className="flex items-center justify-center gap-2">{NEXT_LABEL[status]} <ChevronRight className="w-4 h-4"/></span>}
              </button>
            ) : (
              <div className="flex items-center justify-center gap-2 text-emerald-300 text-sm py-3">
                <CheckCircle2 className="w-4 h-4"/> trip complete
              </div>
            )}
          </div>
        ) : (
          <div className="absolute left-3 right-3 bottom-3 sm:left-auto sm:right-3 sm:bottom-3 sm:w-[360px]
                          card p-4 backdrop-blur-md bg-ink-900/85 z-[400]">
            <div className="flex items-center gap-2 text-emerald-300 mb-1">
              <CheckCircle2 className="w-4 h-4"/>
              <div className="text-sm font-semibold">Available</div>
            </div>
            <div className="text-xs text-slate-400">
              {amb.paramedic_name && <>Crew: {amb.paramedic_name}<br/></>}
              GPS pushing every few seconds. Stand by for dispatch.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


// ── First-run claim picker ─────────────────────────────────────────────────
function ClaimScreen({ fleet, onClaim, busy, user, onLogout }) {
  return (
    <div className="min-h-screen bg-ink-950 text-slate-100">
      <header className="border-b border-line/60 bg-ink-900/60 px-6 py-3 flex items-center gap-3">
        <Truck className="w-5 h-5 text-cyan-400"/>
        <div className="flex-1">
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">paramedic</div>
          <div className="text-sm font-semibold">{user?.full_name || user?.username}</div>
        </div>
        <button onClick={onLogout} className="btn-ghost text-xs px-3 py-1.5">
          <LogOut className="w-3.5 h-3.5"/>logout
        </button>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="card p-6">
          <h1 className="text-xl font-bold mb-1">Claim your ambulance</h1>
          <p className="text-sm text-slate-400 mb-4">
            Pick the unit you'll be driving today. You'll get GPS push, dispatch
            assignments, and the patient briefing screen.
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {fleet.length === 0 && (
              <div className="text-sm text-slate-500 col-span-2">No ambulances available right now.</div>
            )}
            {fleet.map(a => (
              <button key={a.id} onClick={() => onClaim(a.id)} disabled={busy || !!a.assigned_user_id}
                      className="text-left card p-3 hover:border-cyan-400/40 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
                <div className="font-mono text-sm">{a.registration_number}</div>
                <div className="text-[11px] text-slate-500 flex gap-2 mt-0.5">
                  <span>{a.ambulance_type.toUpperCase()}</span>
                  <span>·</span>
                  <span className="text-slate-400">{a.status}</span>
                </div>
                {a.assigned_user_id && (
                  <div className="text-[10px] text-amber-300 mt-1">already claimed</div>
                )}
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
