import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle, Heart, FileText, Upload, Trash2, MapPin, Phone,
  ShieldAlert, Loader2, LogOut, Activity, Clock, CheckCircle2,
} from 'lucide-react'

import { patientApi } from '../api/client.js'
import { useAuthStore } from '../store/auth.js'
import { useUiStore } from '../store/ui.js'

const RECORD_TYPES = [
  { v: 'mri',                label: 'MRI' },
  { v: 'ct_scan',            label: 'CT scan' },
  { v: 'xray',               label: 'X-ray' },
  { v: 'ecg',                label: 'ECG' },
  { v: 'blood_test',         label: 'Blood test' },
  { v: 'prescription',       label: 'Prescription' },
  { v: 'discharge_summary',  label: 'Discharge summary' },
  { v: 'other',              label: 'Other' },
]

const initialProfile = {
  full_name: '', date_of_birth: '', gender: 'male',
  blood_group: '', phone: '', address: '',
  allergies: '', chronic_conditions: '', current_medications: '',
  emergency_contact_name: '', emergency_contact_phone: '',
  emergency_contact_relation: '',
}

export default function PatientDashboard() {
  const nav = useNavigate()
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const toast = useUiStore(s => s.toast)

  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState(initialProfile)
  const [editing, setEditing] = useState(false)
  const [records, setRecords] = useState([])
  const [active, setActive] = useState(null)
  const [busy, setBusy] = useState(false)
  const [sosBusy, setSosBusy] = useState(false)
  const [coords, setCoords] = useState(null)

  // ── Initial load ─────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const p = await patientApi.myProfile()
        setProfile(p); setDraft({ ...initialProfile, ...p })
      } catch (err) {
        if (err?.response?.status === 404) setEditing(true)
        else toast(err?.response?.data?.detail || 'Profile load failed', 'critical')
      }
      try { setRecords(await patientApi.listRecords()) } catch { /* no profile */ }
      try { setActive(await patientApi.activeEmergency()) } catch { /* no profile */ }
    })()
  }, [])

  // Re-poll active emergency every 8s while one exists.
  useEffect(() => {
    if (!active) return
    const t = setInterval(async () => {
      try { setActive(await patientApi.activeEmergency()) } catch {}
    }, 8000)
    return () => clearInterval(t)
  }, [active?.id])

  // ── Geolocation ──────────────────────────────────────────────
  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      pos => setCoords([pos.coords.latitude, pos.coords.longitude]),
      () => { /* user denied — SOS will fall back to profile address */ },
      { enableHighAccuracy: true, timeout: 4000 },
    )
  }, [])

  // ── Profile save ─────────────────────────────────────────────
  async function saveProfile(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const payload = { ...draft }
      // Empty strings → undefined so the backend doesn't reject ints/dates.
      Object.keys(payload).forEach(k => { if (payload[k] === '') delete payload[k] })
      const fn = profile ? patientApi.updateProfile : patientApi.createProfile
      const p = await fn(payload)
      setProfile(p); setEditing(false)
      toast('Profile saved', 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Save failed', 'critical')
    } finally { setBusy(false) }
  }

  // ── Record upload ────────────────────────────────────────────
  const fileInputRef = useRef(null)
  const [uploadType, setUploadType] = useState('blood_test')
  const [uploadDesc, setUploadDesc] = useState('')

  async function handleUpload(e) {
    const f = e.target.files?.[0]; if (!f) return
    if (f.size > 15 * 1024 * 1024) {
      toast('File too large (15MB max)', 'critical'); return
    }
    setBusy(true)
    try {
      const rec = await patientApi.uploadRecord(f, uploadType, uploadDesc)
      setRecords(rs => [rec, ...rs])
      setUploadDesc('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      toast(`${rec.file_name} uploaded`, 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Upload failed', 'critical')
    } finally { setBusy(false) }
  }

  async function deleteRecord(id) {
    if (!confirm('Delete this record? This cannot be undone.')) return
    try {
      await patientApi.deleteRecord(id)
      setRecords(rs => rs.filter(r => r.id !== id))
      toast('Record deleted', 'info')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Delete failed', 'critical')
    }
  }

  // ── SOS ──────────────────────────────────────────────────────
  async function raiseSos() {
    if (!profile) {
      toast('Save your profile first so the responders know who you are.', 'critical')
      return
    }
    if (!coords) {
      toast('Need your GPS — please allow location access.', 'critical')
      return
    }
    if (!confirm('Raise an emergency SOS now?')) return
    setSosBusy(true)
    try {
      const r = await patientApi.raiseSos({
        location_lat: coords[0],
        location_lng: coords[1],
        symptoms: [],
        chief_complaint: 'Patient SOS',
      })
      toast(r.message, r.dispatch_id ? 'success' : 'critical', 9000)
      setActive(await patientApi.activeEmergency())
    } catch (err) {
      toast(err?.response?.data?.detail || 'SOS failed', 'critical')
    } finally { setSosBusy(false) }
  }

  return (
    <div className="min-h-screen bg-ink-950 text-slate-100">
      {/* Top bar */}
      <header className="border-b border-line/60 bg-ink-900/60 backdrop-blur sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-4">
          <Heart className="w-5 h-5 text-sig-critical"/>
          <div className="flex-1">
            <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">
              RapidEMS · patient
            </div>
            <div className="text-sm font-semibold">{user?.full_name || user?.username}</div>
          </div>
          <button onClick={() => { logout(); nav('/login') }}
                  className="btn-ghost text-xs px-3 py-1.5">
            <LogOut className="w-3.5 h-3.5"/>logout
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-8">
        {/* Active emergency banner */}
        {active && (
          <div className="card p-4 border-sig-critical/50 shadow-glow-red animate-pulse-slow">
            <div className="flex items-center gap-3 mb-2">
              <Activity className="w-5 h-5 text-sig-critical"/>
              <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-sig-critical">
                Active emergency
              </div>
            </div>
            <div className="text-lg font-semibold">
              Help is on the way — emergency #{active.id}
            </div>
            <div className="text-sm text-slate-400 mt-1">
              Severity {active.predicted_severity ?? '—'} ·
              status <span className="font-mono">{active.status}</span>
            </div>
          </div>
        )}

        {/* SOS */}
        <section className="card p-6 border-sig-critical/30">
          <div className="flex items-center gap-3 mb-4">
            <ShieldAlert className="w-6 h-6 text-sig-critical"/>
            <h2 className="text-xl font-bold">Emergency SOS</h2>
          </div>
          <p className="text-sm text-slate-400 mb-4">
            One tap dispatches the nearest ambulance to your current location and
            alerts the best-fit hospital with your medical record summary.
          </p>
          <div className="flex items-center gap-3 mb-4 text-xs font-mono text-slate-500">
            <MapPin className="w-3.5 h-3.5"/>
            {coords
              ? `GPS lock ${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`
              : 'awaiting GPS permission…'}
          </div>
          <button
            onClick={raiseSos}
            disabled={sosBusy || !!active}
            className="w-full py-4 rounded-lg bg-sig-critical hover:bg-sig-critical/90 text-white font-bold text-lg
                       disabled:opacity-40 disabled:cursor-not-allowed shadow-glow-red transition-all"
          >
            {sosBusy
              ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-5 h-5 animate-spin"/>dispatching…</span>
              : active
                ? 'help is already on the way'
                : 'RAISE SOS NOW'}
          </button>
        </section>

        {/* Profile */}
        <section className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Heart className="w-5 h-5 text-sig-serious"/>
              <h2 className="text-xl font-bold">My medical profile</h2>
            </div>
            {!editing && (
              <button onClick={() => setEditing(true)} className="btn-ghost text-xs">
                {profile ? 'edit' : 'create profile'}
              </button>
            )}
          </div>

          {editing ? (
            <form onSubmit={saveProfile} className="grid sm:grid-cols-2 gap-3">
              <Field label="Full name *">
                <input className="field" required value={draft.full_name}
                       onChange={e => setDraft({...draft, full_name: e.target.value})}/>
              </Field>
              <Field label="Date of birth">
                <input type="date" className="field" value={draft.date_of_birth || ''}
                       onChange={e => setDraft({...draft, date_of_birth: e.target.value})}/>
              </Field>
              <Field label="Gender">
                <select className="field" value={draft.gender}
                        onChange={e => setDraft({...draft, gender: e.target.value})}>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </Field>
              <Field label="Blood group">
                <input className="field font-mono" placeholder="O+, A-, …"
                       value={draft.blood_group}
                       onChange={e => setDraft({...draft, blood_group: e.target.value})}/>
              </Field>
              <Field label="Phone">
                <input className="field font-mono" value={draft.phone}
                       onChange={e => setDraft({...draft, phone: e.target.value})}/>
              </Field>
              <Field label="Address" wide>
                <input className="field" value={draft.address}
                       onChange={e => setDraft({...draft, address: e.target.value})}/>
              </Field>
              <Field label="Allergies" wide>
                <textarea className="field min-h-[60px]" value={draft.allergies}
                          onChange={e => setDraft({...draft, allergies: e.target.value})}/>
              </Field>
              <Field label="Chronic conditions" wide>
                <textarea className="field min-h-[60px]" value={draft.chronic_conditions}
                          onChange={e => setDraft({...draft, chronic_conditions: e.target.value})}/>
              </Field>
              <Field label="Current medications" wide>
                <textarea className="field min-h-[60px]" value={draft.current_medications}
                          onChange={e => setDraft({...draft, current_medications: e.target.value})}/>
              </Field>
              <Field label="Emergency contact name">
                <input className="field" value={draft.emergency_contact_name}
                       onChange={e => setDraft({...draft, emergency_contact_name: e.target.value})}/>
              </Field>
              <Field label="Emergency contact phone">
                <input className="field font-mono" value={draft.emergency_contact_phone}
                       onChange={e => setDraft({...draft, emergency_contact_phone: e.target.value})}/>
              </Field>

              <div className="sm:col-span-2 flex gap-2 pt-2 border-t border-line/40">
                <button type="submit" disabled={busy} className="btn-danger flex-1">
                  {busy ? 'Saving…' : 'Save profile'}
                </button>
                {profile && (
                  <button type="button"
                          onClick={() => { setDraft({...initialProfile, ...profile}); setEditing(false) }}
                          className="btn-ghost px-4">
                    Cancel
                  </button>
                )}
              </div>
            </form>
          ) : profile ? (
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <Pair label="Name"          value={profile.full_name}/>
              <Pair label="DOB"           value={profile.date_of_birth || '—'}/>
              <Pair label="Gender"        value={profile.gender || '—'}/>
              <Pair label="Blood group"   value={profile.blood_group || '—'} mono/>
              <Pair label="Phone"         value={profile.phone || '—'} mono/>
              <Pair label="Address"       value={profile.address || '—'}/>
              <Pair label="Allergies"     value={profile.allergies || '—'}/>
              <Pair label="Chronic"       value={profile.chronic_conditions || '—'}/>
              <Pair label="Medications"   value={profile.current_medications || '—'}/>
              <Pair label="NoK"           value={profile.emergency_contact_name
                                                   ? `${profile.emergency_contact_name} (${profile.emergency_contact_phone || '—'})`
                                                   : '—'}/>
            </div>
          ) : (
            <div className="text-sm text-slate-500">No profile yet — fill it in so responders have your context on SOS.</div>
          )}
        </section>

        {/* Medical records */}
        <section className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="w-5 h-5 text-cyan-400"/>
            <h2 className="text-xl font-bold">Medical records</h2>
            <span className="text-xs font-mono text-slate-500">{records.length} files</span>
          </div>

          <div className="grid sm:grid-cols-3 gap-3 mb-3">
            <select className="field" value={uploadType}
                    onChange={e => setUploadType(e.target.value)}>
              {RECORD_TYPES.map(t => <option key={t.v} value={t.v}>{t.label}</option>)}
            </select>
            <input className="field sm:col-span-2" placeholder="Description (optional)"
                   value={uploadDesc} onChange={e => setUploadDesc(e.target.value)}/>
          </div>
          <input ref={fileInputRef} type="file"
                 onChange={handleUpload} disabled={busy || !profile}
                 className="block w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4
                            file:rounded file:border-0 file:bg-cyan-400/10
                            file:text-cyan-300 hover:file:bg-cyan-400/20
                            disabled:opacity-40"/>
          {!profile && (
            <div className="text-xs text-amber-400/80 mt-2">
              Save your profile first to upload records.
            </div>
          )}

          <div className="mt-4 divide-y divide-line/40">
            {records.length === 0 && (
              <div className="text-sm text-slate-500 py-4">No records uploaded yet.</div>
            )}
            {records.map(r => (
              <div key={r.id} className="py-3 flex items-center gap-3">
                <FileText className="w-4 h-4 text-slate-500"/>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-mono truncate">{r.file_name}</div>
                  <div className="text-[11px] text-slate-500 flex gap-2 flex-wrap mt-0.5">
                    <span>{r.record_type}</span>
                    <span>·</span>
                    <span>{(r.file_size/1024).toFixed(1)} KB</span>
                    <span>·</span>
                    <span>{new Date(r.uploaded_at).toLocaleString()}</span>
                    {r.description && <><span>·</span><span>{r.description}</span></>}
                  </div>
                </div>
                <a href={`/api${patientApi.downloadRecordUrl(r.id)}`}
                   onClick={e => { e.preventDefault();
                     /* Use authenticated axios so the JWT is attached. */
                     window.location = patientApi.downloadRecordUrl(r.id) }}
                   className="btn-ghost text-xs">view</a>
                <button onClick={() => deleteRecord(r.id)} className="btn-ghost text-xs text-red-300">
                  <Trash2 className="w-3.5 h-3.5"/>
                </button>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

// ── small helpers ──
function Field({ label, children, wide }) {
  return (
    <div className={wide ? 'sm:col-span-2' : ''}>
      <label className="field-label">{label}</label>
      {children}
    </div>
  )
}

function Pair({ label, value, mono }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-sm ${mono ? 'font-mono' : ''}`}>{value}</div>
    </div>
  )
}
