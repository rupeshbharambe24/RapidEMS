import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Hospital as HospitalIcon, Activity, BedDouble, Heart, Loader2,
  CheckCircle2, AlertTriangle, ShieldOff, LogOut, RefreshCw, Phone,
  Clock, FileText, ChevronDown, ChevronUp, Wand2,
} from 'lucide-react'

import { hospitalPortalApi, hospitalsApi } from '../api/client.js'
import { useAuthStore } from '../store/auth.js'
import { useUiStore } from '../store/ui.js'
import { getSocket } from '../api/socket.js'

const STATUS_CHIP = {
  pending:      { label: 'inbound',      cls: 'bg-sig-critical/15 border-sig-critical/50 text-red-200 animate-pulse-slow' },
  acknowledged: { label: 'acknowledged', cls: 'bg-amber-400/15 border-amber-400/50 text-amber-200' },
  accepted:     { label: 'accepted',     cls: 'bg-emerald-400/15 border-emerald-400/50 text-emerald-200' },
  diverted:     { label: 'diverted',     cls: 'bg-slate-500/15 border-slate-500/50 text-slate-300' },
}

const SEV_TINT = ['', 'border-sig-critical/60', 'border-sig-serious/60',
                  'border-sig-moderate/60', 'border-cyan-400/40', 'border-emerald-400/30']

export default function HospitalPortal() {
  const nav = useNavigate()
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const toast = useUiStore(s => s.toast)

  const [snap, setSnap] = useState(null)
  const [allHosp, setAllHosp] = useState([])
  const [busy, setBusy] = useState(false)

  // ── Initial load + claim picker if no hospital yet ──────────────────────
  useEffect(() => {
    (async () => {
      try {
        setSnap(await hospitalPortalApi.me())
      } catch (err) {
        if (err?.response?.status === 409) {
          try { setAllHosp(await hospitalsApi.list()) } catch {}
        } else {
          toast(err?.response?.data?.detail || 'Portal load failed', 'critical')
        }
      }
    })()
  }, [])

  // ── Re-poll every 6s for ETA tick + new alerts ──────────────────────────
  useEffect(() => {
    if (!snap) return
    const t = setInterval(async () => {
      try { setSnap(await hospitalPortalApi.me()) } catch {}
    }, 6000)
    return () => clearInterval(t)
  }, [snap?.hospital?.id])

  // ── Real-time alert push ────────────────────────────────────────────────
  useEffect(() => {
    if (!snap) return
    const sock = getSocket(); if (!sock) return
    const onAlert = (msg) => {
      if (msg.hospital_id !== snap.hospital.id) return
      toast(`Inbound: SEV-${msg.severity_level} · ETA ${msg.eta_minutes}m · ${msg.ambulance_registration}`,
            'critical', 8000)
      hospitalPortalApi.me().then(setSnap).catch(() => {})
    }
    const onStatus = (msg) => {
      if (msg.hospital_id !== snap.hospital.id) return
      hospitalPortalApi.me().then(setSnap).catch(() => {})
    }
    sock.on('hospital:alert', onAlert)
    sock.on('hospital:alert_status', onStatus)
    return () => {
      sock.off('hospital:alert', onAlert)
      sock.off('hospital:alert_status', onStatus)
    }
  }, [snap?.hospital?.id])

  async function claim(hid) {
    setBusy(true)
    try {
      await hospitalPortalApi.claim(hid)
      setSnap(await hospitalPortalApi.me())
    } catch (err) {
      toast(err?.response?.data?.detail || 'Claim failed', 'critical')
    } finally { setBusy(false) }
  }

  async function release() {
    if (!confirm('Release this hospital?')) return
    try {
      await hospitalPortalApi.release()
      setSnap(null); setAllHosp(await hospitalsApi.list())
    } catch (err) {
      toast(err?.response?.data?.detail || 'Release failed', 'critical')
    }
  }

  async function actOn(id, kind) {
    setBusy(true)
    try {
      const fn = kind === 'ack' ? hospitalPortalApi.acknowledge
              : kind === 'accept' ? hospitalPortalApi.accept
              : kind === 'divert' ? hospitalPortalApi.divert
              : kind === 'regen'  ? hospitalPortalApi.regenerateBriefing
              : null
      if (!fn) return
      await fn(id)
      setSnap(await hospitalPortalApi.me())
      if (kind === 'regen') toast('Briefing regenerated', 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || `${kind} failed`, 'critical')
    } finally { setBusy(false) }
  }

  // ─────────────────────────────────────────────────────────────────────────
  if (!snap) return (
    <ClaimScreen all={allHosp} onClaim={claim} busy={busy}
                 user={user} onLogout={() => { logout(); nav('/login') }}/>
  )

  const h = snap.hospital
  const alerts = snap.alerts

  return (
    <div className="min-h-screen bg-ink-950 text-slate-100">
      {/* Top bar */}
      <header className="border-b border-line/60 bg-ink-900/60 backdrop-blur sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-4">
          <HospitalIcon className="w-5 h-5 text-emerald-400"/>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">hospital portal</div>
            <div className="text-sm font-semibold truncate">{h.name}</div>
          </div>
          {h.is_diversion && (
            <div className="px-2 py-1 rounded border border-amber-400/60 text-amber-200 text-[10px] font-mono uppercase">
              on diversion
            </div>
          )}
          <button onClick={release} className="btn-ghost text-xs px-3 py-1.5"
                  title="Switch hospital">
            <RefreshCw className="w-3.5 h-3.5"/>
          </button>
          <button onClick={() => { logout(); nav('/login') }}
                  className="btn-ghost text-xs px-3 py-1.5">
            <LogOut className="w-3.5 h-3.5"/>
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 grid lg:grid-cols-3 gap-6">
        {/* ── Inbound alerts ────────────────────────────────────── */}
        <section className="lg:col-span-2 card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="w-5 h-5 text-sig-critical"/>
            <h2 className="text-xl font-bold">Inbound alerts</h2>
            <span className="text-xs font-mono text-slate-500">
              {snap.open_alerts} open · {alerts.length} total
            </span>
          </div>
          {alerts.length === 0 && (
            <div className="text-sm text-slate-500 py-6">
              No incoming dispatches yet.
            </div>
          )}
          <div className="space-y-3">
            {alerts.map(a => (
              <AlertCard key={a.id} alert={a} busy={busy}
                         onAct={(kind) => actOn(a.id, kind)}/>
            ))}
          </div>
        </section>

        {/* ── Bed editor ────────────────────────────────────────── */}
        <section className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <BedDouble className="w-5 h-5 text-cyan-400"/>
            <h2 className="text-lg font-bold">Bed availability</h2>
          </div>
          <BedEditor hospital={h} onSaved={async () => {
            setSnap(await hospitalPortalApi.me())
            toast('Beds updated', 'success')
          }}/>
        </section>
      </main>
    </div>
  )
}


// ── Alert card ─────────────────────────────────────────────────────────────
function AlertCard({ alert, busy, onAct }) {
  const [showBriefing, setShowBriefing] = useState(false)
  const e = alert.emergency
  const sev = alert.severity_level || 0
  const chip = STATUS_CHIP[alert.status] || STATUS_CHIP.pending
  const minsAgo = useMinsSince(alert.created_at)
  const open = alert.status === 'pending' || alert.status === 'acknowledged'

  return (
    <div className={`card p-4 border ${SEV_TINT[sev] || 'border-line/40'}`}>
      <div className="flex items-start gap-3">
        <Heart className="w-4 h-4 text-sig-critical mt-0.5 shrink-0"/>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold">
              SEV-{sev} {e?.patient_name ? `· ${e.patient_name}` : ''}
              {e?.patient_age ? `, ${e.patient_age}` : ''}
              {e?.patient_gender ? ` (${e.patient_gender})` : ''}
            </span>
            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono uppercase tracking-wider ${chip.cls}`}>
              {chip.label}
            </span>
            {alert.patient_type && (
              <span className="text-[10px] font-mono text-slate-500 uppercase">
                {alert.patient_type}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3"/>
              ETA {alert.eta_minutes ?? '?'}m
            </span>
            <span>· {alert.ambulance_registration || '—'}</span>
            <span>· {minsAgo}m ago</span>
            {e?.phone && (
              <a className="text-cyan-300 inline-flex items-center gap-1" href={`tel:${e.phone}`}>
                <Phone className="w-3 h-3"/>{e.phone}
              </a>
            )}
          </div>
          {e?.symptoms?.length > 0 && (
            <div className="text-xs text-slate-300 mt-1.5">
              {e.symptoms.slice(0, 4).map(s => s.replaceAll('_', ' ')).join(' · ')}
            </div>
          )}
          {e?.chief_complaint && (
            <div className="text-xs italic text-slate-500 mt-1">
              "{e.chief_complaint}"
            </div>
          )}
        </div>
      </div>

      {/* ER briefing */}
      <div className="mt-3 pt-3 border-t border-line/30">
        <button onClick={() => setShowBriefing(v => !v)}
                className="w-full flex items-center justify-between gap-2 text-xs font-mono uppercase tracking-wider text-slate-400 hover:text-slate-200 transition-colors">
          <span className="flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5"/>
            ER briefing
            {!alert.briefing && <span className="text-slate-600 normal-case">— generating…</span>}
          </span>
          {showBriefing
            ? <ChevronUp className="w-3.5 h-3.5"/>
            : <ChevronDown className="w-3.5 h-3.5"/>}
        </button>
        {showBriefing && (
          <div className="mt-2 p-3 rounded bg-ink-700/40 border border-line/30">
            {alert.briefing ? (
              <pre className="text-xs whitespace-pre-wrap font-mono text-slate-200 leading-relaxed">
                {alert.briefing}
              </pre>
            ) : (
              <div className="text-xs text-slate-500 italic">
                The LLM briefing is still generating. Try regenerate in a moment.
              </div>
            )}
            <button onClick={() => onAct('regen')} disabled={busy}
                    className="mt-2 btn-ghost text-[10px]">
              <Wand2 className="w-3 h-3"/>regenerate briefing
            </button>
          </div>
        )}
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-line/30 flex flex-wrap gap-2">
          {alert.status === 'pending' && (
            <button onClick={() => onAct('ack')} disabled={busy}
                    className="btn-ghost text-xs">
              <CheckCircle2 className="w-3.5 h-3.5"/>acknowledge
            </button>
          )}
          <button onClick={() => onAct('accept')} disabled={busy}
                  className="btn-ghost text-xs text-emerald-300 border-emerald-400/40">
            <CheckCircle2 className="w-3.5 h-3.5"/>accept
          </button>
          <button onClick={() => onAct('divert')} disabled={busy}
                  className="btn-ghost text-xs text-amber-300 border-amber-400/40">
            <ShieldOff className="w-3.5 h-3.5"/>divert
          </button>
        </div>
      )}
    </div>
  )
}


// ── Bed editor ─────────────────────────────────────────────────────────────
function BedEditor({ hospital, onSaved }) {
  const [draft, setDraft] = useState({
    available_beds_general: hospital.available_beds_general ?? 0,
    available_beds_icu:     hospital.available_beds_icu ?? 0,
    available_beds_trauma:  hospital.available_beds_trauma ?? 0,
    available_beds_pediatric: hospital.available_beds_pediatric ?? 0,
    available_beds_burns:   hospital.available_beds_burns ?? 0,
    er_wait_minutes:        hospital.er_wait_minutes ?? 0,
    is_diversion:           !!hospital.is_diversion,
  })
  const [busy, setBusy] = useState(false)
  const toast = useUiStore(s => s.toast)

  // Re-sync if hospital changes externally (websocket update).
  useEffect(() => {
    setDraft({
      available_beds_general: hospital.available_beds_general ?? 0,
      available_beds_icu:     hospital.available_beds_icu ?? 0,
      available_beds_trauma:  hospital.available_beds_trauma ?? 0,
      available_beds_pediatric: hospital.available_beds_pediatric ?? 0,
      available_beds_burns:   hospital.available_beds_burns ?? 0,
      er_wait_minutes:        hospital.er_wait_minutes ?? 0,
      is_diversion:           !!hospital.is_diversion,
    })
  }, [hospital])

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await hospitalPortalApi.updateBeds(draft)
      onSaved?.()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Save failed', 'critical')
    } finally { setBusy(false) }
  }

  const Row = ({ label, total, k }) => (
    <div className="flex items-center gap-3">
      <div className="flex-1 text-sm">
        <div>{label}</div>
        <div className="text-[10px] font-mono text-slate-500">of {total}</div>
      </div>
      <input type="number" min="0" max={total ?? 999}
             className="field font-mono w-24 text-right"
             value={draft[k]}
             onChange={e => setDraft({ ...draft, [k]: Math.max(0, parseInt(e.target.value || '0')) })}/>
    </div>
  )

  return (
    <form onSubmit={save} className="space-y-3">
      <Row label="General"   total={hospital.total_beds_general}   k="available_beds_general"/>
      <Row label="ICU"       total={hospital.total_beds_icu}       k="available_beds_icu"/>
      <Row label="Trauma"    total={hospital.total_beds_trauma}    k="available_beds_trauma"/>
      <Row label="Pediatric" total={hospital.total_beds_pediatric} k="available_beds_pediatric"/>
      <Row label="Burns"     total={hospital.total_beds_burns}     k="available_beds_burns"/>
      <div className="pt-3 border-t border-line/30 space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex-1 text-sm">ER wait (min)</div>
          <input type="number" min="0" className="field font-mono w-24 text-right"
                 value={draft.er_wait_minutes}
                 onChange={e => setDraft({ ...draft, er_wait_minutes: Math.max(0, parseInt(e.target.value || '0')) })}/>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={draft.is_diversion}
                 onChange={e => setDraft({ ...draft, is_diversion: e.target.checked })}/>
          On diversion
        </label>
      </div>
      <button type="submit" disabled={busy}
              className="w-full btn-danger disabled:opacity-40">
        {busy ? <Loader2 className="w-4 h-4 animate-spin"/> : 'Save'}
      </button>
    </form>
  )
}


// ── Claim picker (first run) ──────────────────────────────────────────────
function ClaimScreen({ all, onClaim, busy, user, onLogout }) {
  return (
    <div className="min-h-screen bg-ink-950 text-slate-100">
      <header className="border-b border-line/60 bg-ink-900/60 px-6 py-3 flex items-center gap-3">
        <HospitalIcon className="w-5 h-5 text-emerald-400"/>
        <div className="flex-1">
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">hospital staff</div>
          <div className="text-sm font-semibold">{user?.full_name || user?.username}</div>
        </div>
        <button onClick={onLogout} className="btn-ghost text-xs px-3 py-1.5">
          <LogOut className="w-3.5 h-3.5"/>logout
        </button>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="card p-6">
          <h1 className="text-xl font-bold mb-1">Pick your hospital</h1>
          <p className="text-sm text-slate-400 mb-4">
            Select the facility you'll be staffing. You'll see inbound dispatches,
            manage beds, and accept or divert patients in real time.
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {all.length === 0 && (
              <div className="text-sm text-slate-500 col-span-2">No hospitals available right now.</div>
            )}
            {all.map(h => (
              <button key={h.id} onClick={() => onClaim(h.id)} disabled={busy}
                      className="text-left card p-3 hover:border-emerald-400/40 disabled:opacity-40 transition-all">
                <div className="text-sm font-semibold truncate">{h.name}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {h.specialties?.slice(0,3).join(' · ') || '—'}
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-1">
                  {h.available_beds_general}/{h.total_beds_general} general ·
                  {h.available_beds_icu}/{h.total_beds_icu} ICU
                </div>
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}


function useMinsSince(iso) {
  const [n, set] = useState(() => Math.max(0, Math.floor((Date.now() - new Date(iso)) / 60000)))
  useEffect(() => {
    const t = setInterval(() =>
      set(Math.max(0, Math.floor((Date.now() - new Date(iso)) / 60000))), 30_000)
    return () => clearInterval(t)
  }, [iso])
  return n
}
