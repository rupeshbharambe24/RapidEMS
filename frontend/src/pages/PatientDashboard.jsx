import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle, Heart, FileText, Upload, Trash2, MapPin, Phone,
  ShieldAlert, Loader2, LogOut, Activity, Clock, CheckCircle2,
  Bell, Send, Mail, MessageCircle, ExternalLink, Plus, X,
  Share2, Copy, ShieldOff, Users, Watch, Droplet, Wind, Thermometer,
} from 'lucide-react'

import { patientApi, notificationsApi, trackingApi, telemetryApi } from '../api/client.js'
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

        {/* Wearable telemetry */}
        <WearableCard/>

        {/* Notifications */}
        <NotificationsCard/>

        {/* Family tracking */}
        <FamilyTrackingCard/>

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

// ── Wearable card ──────────────────────────────────────────────────────────
function WearableCard() {
  const toast = useUiStore(s => s.toast)
  const [latest, setLatest] = useState(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState({
    source: 'manual',
    heart_rate: '', spo2: '',
    blood_pressure_systolic: '', blood_pressure_diastolic: '',
    respiratory_rate: '', body_temperature_c: '', glucose_mg_dl: '',
  })
  const [showAdd, setShowAdd] = useState(false)

  async function refresh() {
    try { setLatest(await telemetryApi.latest()) }
    catch (err) {
      if (err?.response?.status === 409) setLatest(null) // no profile yet
      else toast(err?.response?.data?.detail || 'Telemetry load failed', 'critical')
    }
  }
  useEffect(() => { refresh() }, [])

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const reading = { source: draft.source }
      const numKeys = ['heart_rate','spo2','blood_pressure_systolic',
                       'blood_pressure_diastolic','respiratory_rate',
                       'body_temperature_c','glucose_mg_dl']
      for (const k of numKeys) {
        if (draft[k] !== '') reading[k] = parseFloat(draft[k])
      }
      if (Object.keys(reading).length <= 1) {
        toast('Enter at least one reading.', 'critical'); setBusy(false); return
      }
      const r = await telemetryApi.ingest([reading])
      toast(`${r.inserted} reading saved`, 'success')
      setDraft({ source:'manual', heart_rate:'', spo2:'',
                 blood_pressure_systolic:'', blood_pressure_diastolic:'',
                 respiratory_rate:'', body_temperature_c:'', glucose_mg_dl:'' })
      setShowAdd(false)
      refresh()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Save failed', 'critical')
    } finally { setBusy(false) }
  }

  const Tile = ({ icon: Icon, label, value, unit, at, tint }) => (
    <div className={`card p-3 border ${tint || 'border-line/40'}`}>
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-500">
        <Icon className="w-3 h-3"/>{label}
      </div>
      <div className="text-2xl font-bold mt-0.5 leading-none">
        {value ?? '—'}<span className="text-xs text-slate-400 ml-1">{value != null && unit}</span>
      </div>
      <div className="text-[10px] text-slate-500 mt-1">
        {at ? new Date(at).toLocaleString() : 'no readings yet'}
      </div>
    </div>
  )

  const hr = latest?.heart_rate
  const spo2 = latest?.spo2
  const tempC = latest?.body_temperature_c
  const glucose = latest?.glucose_mg_dl

  return (
    <section className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Watch className="w-5 h-5 text-cyan-300"/>
          <h2 className="text-xl font-bold">Wearable readings</h2>
        </div>
        <button onClick={() => setShowAdd(true)} className="btn-ghost text-xs">
          <Plus className="w-3.5 h-3.5"/>add reading
        </button>
      </div>

      <div className="text-xs text-slate-500 mb-4">
        Latest values from your watch / BP cuff / glucometer. When you raise an
        SOS, these are auto-injected into the dispatcher's view so the AI sees
        real numbers, not guesses.
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile icon={Heart}      label="Heart rate" value={hr}    unit="bpm"
              at={latest?.heart_rate_at}
              tint={hr != null && (hr < 50 || hr > 110) ? 'border-amber-400/40' : ''}/>
        <Tile icon={Wind}       label="SpO₂"        value={spo2}  unit="%"
              at={latest?.spo2_at}
              tint={spo2 != null && spo2 < 92 ? 'border-sig-critical/40' :
                    spo2 != null && spo2 < 95 ? 'border-amber-400/40' : ''}/>
        <Tile icon={Activity}   label="Blood pressure"
              value={latest?.blood_pressure_systolic
                       ? `${latest.blood_pressure_systolic}/${latest.blood_pressure_diastolic}`
                       : null}
              unit="mmHg" at={latest?.blood_pressure_at}/>
        <Tile icon={Thermometer} label="Temp" value={tempC} unit="°C"
              at={latest?.body_temperature_at}
              tint={tempC != null && tempC >= 38 ? 'border-amber-400/40' : ''}/>
        <Tile icon={Droplet}    label="Glucose" value={glucose} unit="mg/dL"
              at={latest?.glucose_at}
              tint={glucose != null && (glucose < 70 || glucose > 200) ? 'border-amber-400/40' : ''}/>
        <Tile icon={Wind}       label="Resp rate" value={latest?.respiratory_rate}
              unit="/min" at={latest?.respiratory_rate_at}/>
        <Tile icon={Activity}   label="Steps today" value={latest?.steps_since_midnight}
              unit="" at={null}/>
        {latest?.fall_detected_at && (
          <Tile icon={AlertCircle} label="Fall detected" value="yes" unit=""
                at={latest.fall_detected_at} tint="border-sig-critical/50"/>
        )}
      </div>

      {showAdd && (
        <form onSubmit={save} className="card p-4 mt-4 space-y-3 border-cyan-400/30">
          <div className="text-sm font-semibold mb-1">Manual reading</div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Heart rate (bpm)">
              <input type="number" min="20" max="250" className="field font-mono"
                     value={draft.heart_rate}
                     onChange={e => setDraft({...draft, heart_rate: e.target.value})}/>
            </Field>
            <Field label="SpO₂ (%)">
              <input type="number" step="0.1" min="40" max="100" className="field font-mono"
                     value={draft.spo2}
                     onChange={e => setDraft({...draft, spo2: e.target.value})}/>
            </Field>
            <Field label="BP systolic">
              <input type="number" min="40" max="260" className="field font-mono"
                     value={draft.blood_pressure_systolic}
                     onChange={e => setDraft({...draft, blood_pressure_systolic: e.target.value})}/>
            </Field>
            <Field label="BP diastolic">
              <input type="number" min="20" max="180" className="field font-mono"
                     value={draft.blood_pressure_diastolic}
                     onChange={e => setDraft({...draft, blood_pressure_diastolic: e.target.value})}/>
            </Field>
            <Field label="Resp rate (/min)">
              <input type="number" min="4" max="60" className="field font-mono"
                     value={draft.respiratory_rate}
                     onChange={e => setDraft({...draft, respiratory_rate: e.target.value})}/>
            </Field>
            <Field label="Temp (°C)">
              <input type="number" step="0.1" min="25" max="45" className="field font-mono"
                     value={draft.body_temperature_c}
                     onChange={e => setDraft({...draft, body_temperature_c: e.target.value})}/>
            </Field>
            <Field label="Glucose (mg/dL)" wide>
              <input type="number" min="20" max="900" className="field font-mono"
                     value={draft.glucose_mg_dl}
                     onChange={e => setDraft({...draft, glucose_mg_dl: e.target.value})}/>
            </Field>
          </div>
          <div className="flex gap-2 pt-2 border-t border-line/30">
            <button type="submit" disabled={busy} className="btn-danger flex-1">
              {busy ? 'Saving…' : 'Save reading'}
            </button>
            <button type="button" onClick={() => setShowAdd(false)}
                    className="btn-ghost px-4">Cancel</button>
          </div>
        </form>
      )}
    </section>
  )
}


// ── Notifications card ─────────────────────────────────────────────────────
function NotificationsCard() {
  const toast = useUiStore(s => s.toast)
  const [caps, setCaps] = useState(null)
  const [subs, setSubs] = useState([])
  const [adding, setAdding] = useState(null)   // 'telegram' | 'email' | null
  const [draft, setDraft] = useState({ target: '', label: '' })
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      const [c, s] = await Promise.all([
        notificationsApi.capabilities(), notificationsApi.list(),
      ])
      setCaps(c); setSubs(s)
    } catch (err) {
      toast(err?.response?.data?.detail || 'Notifications load failed', 'critical')
    }
  }
  useEffect(() => { refresh() }, [])

  async function add(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await notificationsApi.add({
        channel: adding, target: draft.target.trim(), label: draft.label || null,
      })
      setAdding(null); setDraft({ target: '', label: '' })
      refresh()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Add failed', 'critical')
    } finally { setBusy(false) }
  }

  async function test(id) {
    try {
      await notificationsApi.test(id)
      toast('Test message sent', 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Test failed', 'critical')
      refresh()  // pick up last_error
    }
  }

  async function remove(id) {
    if (!confirm('Remove this channel? You will stop getting notifications here.')) return
    try {
      await notificationsApi.remove(id)
      refresh()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Remove failed', 'critical')
    }
  }

  if (!caps) return null

  return (
    <section className="card p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-amber-300"/>
          <h2 className="text-xl font-bold">Notifications</h2>
        </div>
        <div className="flex gap-2">
          <button disabled={!caps.telegram}
                  title={caps.telegram ? '' : 'Telegram not configured on the server'}
                  onClick={() => { setAdding('telegram'); setDraft({ target: '', label: '' }) }}
                  className="btn-ghost text-xs disabled:opacity-40">
            <MessageCircle className="w-3.5 h-3.5"/>add Telegram
          </button>
          <button disabled={!caps.email}
                  title={caps.email ? '' : 'Email not configured on the server'}
                  onClick={() => { setAdding('email'); setDraft({ target: '', label: '' }) }}
                  className="btn-ghost text-xs disabled:opacity-40">
            <Mail className="w-3.5 h-3.5"/>add email
          </button>
        </div>
      </div>

      {!caps.telegram && !caps.email && !caps.sms_twilio && (
        <div className="text-xs text-amber-300/80 mb-3">
          No notification channels are configured on the server yet — set
          <span className="font-mono mx-1">TELEGRAM_BOT_TOKEN</span> or
          <span className="font-mono mx-1">SMTP_*</span> in <span className="font-mono">.env</span>.
        </div>
      )}

      {/* Add dialog */}
      {adding && (
        <form onSubmit={add} className="card p-4 mb-4 space-y-3 border-amber-400/30">
          {adding === 'telegram' ? (
            <>
              <div className="text-sm">
                <div className="font-semibold mb-1">Link Telegram</div>
                <ol className="text-xs text-slate-400 list-decimal list-inside space-y-1">
                  <li>
                    Message <a className="text-cyan-300 hover:underline"
                        href="https://t.me/userinfobot" target="_blank" rel="noreferrer">
                      @userinfobot <ExternalLink className="w-3 h-3 inline"/>
                    </a> on Telegram. It replies with your <span className="font-mono">Id</span>.
                  </li>
                  {caps.telegram_bot_username && (
                    <li>
                      Open the RapidEMS bot:&nbsp;
                      <a className="text-cyan-300 hover:underline"
                         href={`https://t.me/${caps.telegram_bot_username}?start=link`}
                         target="_blank" rel="noreferrer">
                        @{caps.telegram_bot_username} <ExternalLink className="w-3 h-3 inline"/>
                      </a> and tap Start.
                    </li>
                  )}
                  <li>Paste the numeric Id below and Save.</li>
                </ol>
              </div>
              <Field label="Telegram chat ID">
                <input className="field font-mono" required pattern="-?\d+"
                       placeholder="e.g. 123456789"
                       value={draft.target}
                       onChange={e => setDraft({ ...draft, target: e.target.value })}/>
              </Field>
            </>
          ) : (
            <>
              <div className="text-sm font-semibold">Add email address</div>
              <Field label="Email">
                <input type="email" className="field" required
                       value={draft.target}
                       onChange={e => setDraft({ ...draft, target: e.target.value })}/>
              </Field>
            </>
          )}
          <Field label="Label (optional)">
            <input className="field" placeholder="e.g. me, my dad"
                   value={draft.label}
                   onChange={e => setDraft({ ...draft, label: e.target.value })}/>
          </Field>
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="btn-danger flex-1">
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={() => setAdding(null)}
                    className="btn-ghost px-4">Cancel</button>
          </div>
        </form>
      )}

      {/* List */}
      <div className="divide-y divide-line/40">
        {subs.length === 0 && (
          <div className="text-sm text-slate-500 py-3">
            No channels yet. Add Telegram or email to get live updates when help is dispatched.
          </div>
        )}
        {subs.map(s => (
          <div key={s.id} className="py-3 flex items-center gap-3">
            <ChannelIcon channel={s.channel}/>
            <div className="flex-1 min-w-0">
              <div className="text-sm flex items-center gap-2">
                <span className="font-mono truncate">{s.target}</span>
                {s.label && <span className="text-xs text-slate-500">· {s.label}</span>}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                {s.channel}
                {s.last_used_at && <> · last sent {new Date(s.last_used_at).toLocaleString()}</>}
                {s.last_error && (
                  <span className="text-red-400"> · err: {s.last_error.slice(0, 60)}</span>
                )}
              </div>
            </div>
            <button onClick={() => test(s.id)} className="btn-ghost text-xs">
              <Send className="w-3.5 h-3.5"/>test
            </button>
            <button onClick={() => remove(s.id)} className="btn-ghost text-xs text-red-300">
              <Trash2 className="w-3.5 h-3.5"/>
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

function ChannelIcon({ channel }) {
  if (channel === 'telegram') return <MessageCircle className="w-4 h-4 text-cyan-300"/>
  if (channel === 'email')    return <Mail className="w-4 h-4 text-emerald-300"/>
  if (channel === 'sms')      return <Phone className="w-4 h-4 text-amber-300"/>
  return <Bell className="w-4 h-4 text-slate-400"/>
}


// ── Family tracking card ──────────────────────────────────────────────────
function FamilyTrackingCard() {
  const toast = useUiStore(s => s.toast)
  const [links, setLinks] = useState([])
  const [showAdd, setShowAdd] = useState(false)
  const [draft, setDraft] = useState({ emergency_id: '', nok_name: '', nok_phone: '', nok_relation: '', ttl_hours: 4 })
  const [busy, setBusy] = useState(false)
  const [latestToken, setLatestToken] = useState(null)

  async function refresh() {
    try { setLinks(await trackingApi.listMine()) }
    catch (err) { toast(err?.response?.data?.detail || 'Tracking links load failed', 'critical') }
  }
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 8000)
    return () => clearInterval(t)
  }, [])

  async function add(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await trackingApi.createLink({
        emergency_id: parseInt(draft.emergency_id),
        nok_name: draft.nok_name || null,
        nok_phone: draft.nok_phone || null,
        nok_relation: draft.nok_relation || null,
        ttl_hours: draft.ttl_hours,
      })
      setLatestToken(r.token)
      setShowAdd(false)
      setDraft({ emergency_id: '', nok_name: '', nok_phone: '', nok_relation: '', ttl_hours: 4 })
      refresh()
      toast('Tracking link created', 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Create failed', 'critical')
    } finally { setBusy(false) }
  }

  async function revoke(id) {
    if (!confirm('Revoke this tracking link? Anyone holding the URL will lose access.')) return
    try {
      await trackingApi.revoke(id)
      refresh()
      toast('Link revoked', 'info')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Revoke failed', 'critical')
    }
  }

  function urlFor(token) {
    return `${window.location.origin}/track/${token}`
  }
  function copyToClipboard(text) {
    navigator.clipboard?.writeText(text)
      .then(() => toast('Copied to clipboard', 'success'))
      .catch(() => toast('Copy failed — long-press to copy manually', 'critical'))
  }

  const active = links.filter(l => !l.revoked_at && new Date(l.expires_at) > new Date())

  return (
    <section className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Users className="w-5 h-5 text-cyan-300"/>
          <h2 className="text-xl font-bold">Family tracking</h2>
          <span className="text-xs font-mono text-slate-500">
            {active.length} active · {links.length} total
          </span>
        </div>
      </div>

      {/* The token shown only at creation time */}
      {latestToken && (
        <div className="card p-3 mb-3 border-emerald-400/40 bg-emerald-400/5">
          <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-300 mb-1">
            Share this link — visible only now
          </div>
          <div className="flex items-center gap-2 mb-2">
            <code className="flex-1 truncate text-xs font-mono text-emerald-100">
              {urlFor(latestToken)}
            </code>
            <button onClick={() => copyToClipboard(urlFor(latestToken))}
                    className="btn-ghost text-xs">
              <Copy className="w-3.5 h-3.5"/>copy
            </button>
            <button onClick={() => setLatestToken(null)}
                    className="btn-ghost text-xs">
              <X className="w-3.5 h-3.5"/>
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <a href={`https://wa.me/?text=${encodeURIComponent(
                'Live ambulance tracking — ' + urlFor(latestToken))}`}
               target="_blank" rel="noreferrer"
               className="btn-ghost flex-1 !py-1.5 text-emerald-300 border-emerald-400/40">
              <MessageCircle className="w-3.5 h-3.5"/>WhatsApp
            </a>
            <a href={`https://t.me/share/url?url=${encodeURIComponent(urlFor(latestToken))}&text=${encodeURIComponent('Live ambulance tracking')}`}
               target="_blank" rel="noreferrer"
               className="btn-ghost flex-1 !py-1.5 text-cyan-300 border-cyan-400/40">
              <Send className="w-3.5 h-3.5"/>Telegram
            </a>
            <a href={`sms:?body=${encodeURIComponent(
                'Live ambulance tracking — ' + urlFor(latestToken))}`}
               className="btn-ghost flex-1 !py-1.5">
              <Phone className="w-3.5 h-3.5"/>SMS
            </a>
          </div>
        </div>
      )}

      <div className="text-xs text-slate-500 mb-3">
        When you raise an SOS we automatically create a tracking link for the next-of-kin
        on your profile. You can also create extra links manually.
      </div>

      {/* List */}
      <div className="divide-y divide-line/40 mb-3">
        {links.length === 0 && (
          <div className="text-sm text-slate-500 py-3">
            No tracking links yet. Raise an SOS — one will be auto-created if your profile has a next-of-kin contact.
          </div>
        )}
        {links.map(l => {
          const revoked = !!l.revoked_at
          const expired = new Date(l.expires_at) < new Date()
          const dead = revoked || expired
          const expiresMin = Math.max(0, Math.floor((new Date(l.expires_at) - Date.now()) / 60000))
          return (
            <div key={l.id} className="py-3 flex items-center gap-3">
              <Share2 className={`w-4 h-4 shrink-0 ${dead ? 'text-slate-600' : 'text-cyan-300'}`}/>
              <div className="flex-1 min-w-0">
                <div className="text-sm flex items-center gap-2 flex-wrap">
                  <span>Emergency #{l.emergency_id}</span>
                  {l.nok_name && <span className="text-slate-400">· {l.nok_name}</span>}
                  {l.nok_relation && <span className="text-xs text-slate-500">({l.nok_relation})</span>}
                  {revoked && <span className="text-[10px] font-mono uppercase text-amber-300">revoked</span>}
                  {!revoked && expired && <span className="text-[10px] font-mono uppercase text-slate-500">expired</span>}
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                  {l.view_count} views
                  {l.last_seen_at && <> · last seen {new Date(l.last_seen_at).toLocaleString()}</>}
                  {!dead && <> · expires in ~{expiresMin}m</>}
                </div>
              </div>
              {!dead && (
                <button onClick={() => revoke(l.id)}
                        className="btn-ghost text-xs text-amber-300">
                  <ShieldOff className="w-3.5 h-3.5"/>revoke
                </button>
              )}
            </div>
          )
        })}
      </div>

      {/* Manual add */}
      {showAdd ? (
        <form onSubmit={add} className="card p-4 space-y-3 border-cyan-400/30">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Emergency ID *">
              <input type="number" className="field font-mono" required
                     value={draft.emergency_id}
                     onChange={e => setDraft({ ...draft, emergency_id: e.target.value })}/>
            </Field>
            <Field label="TTL (hours)">
              <input type="number" min="1" max="24" className="field font-mono"
                     value={draft.ttl_hours}
                     onChange={e => setDraft({ ...draft, ttl_hours: parseInt(e.target.value || '4') })}/>
            </Field>
            <Field label="NoK name">
              <input className="field" value={draft.nok_name}
                     onChange={e => setDraft({ ...draft, nok_name: e.target.value })}/>
            </Field>
            <Field label="Relation">
              <input className="field" placeholder="mother, brother, …" value={draft.nok_relation}
                     onChange={e => setDraft({ ...draft, nok_relation: e.target.value })}/>
            </Field>
            <Field label="NoK phone" wide>
              <input className="field font-mono" value={draft.nok_phone}
                     onChange={e => setDraft({ ...draft, nok_phone: e.target.value })}/>
            </Field>
          </div>
          <div className="flex gap-2 pt-2 border-t border-line/30">
            <button type="submit" disabled={busy} className="btn-danger flex-1">
              {busy ? 'Creating…' : 'Create link'}
            </button>
            <button type="button" onClick={() => setShowAdd(false)} className="btn-ghost px-4">
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button onClick={() => setShowAdd(true)} className="btn-ghost text-xs">
          <Plus className="w-3.5 h-3.5"/>create link manually
        </button>
      )}
    </section>
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
