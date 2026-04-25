import { useEffect, useMemo, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMapEvents, useMap } from 'react-leaflet'
import { Activity, Send, Sparkles, MapPin, Loader2, MessageSquareText, Wand2 } from 'lucide-react'

import MapView from '../components/MapView.jsx'
import { SeverityPill } from '../components/StatusBadge.jsx'
import { aiApi, emergenciesApi } from '../api/client.js'
import { useUiStore } from '../store/ui.js'

const SYMPTOMS_GROUPS = {
  'Tier 1 — life-threatening': [
    'cardiac_arrest', 'unconscious', 'severe_burns', 'spinal_injury',
    'anaphylaxis', 'major_bleeding',
  ],
  'Tier 2 — serious': [
    'stroke_symptoms', 'chest_pain', 'shortness_of_breath', 'seizure',
    'head_trauma', 'diabetic_emergency',
  ],
  'Tier 3 — moderate': [
    'fracture', 'moderate_bleeding', 'abdominal_pain', 'high_fever',
  ],
  'Tier 4-5 — minor': [
    'vomiting', 'dizziness', 'minor_cut', 'sprain', 'headache',
  ],
}

// Allow user to click on map to set location
function ClickToPlace({ onPick }) {
  useMapEvents({
    click(e) { onPick([e.latlng.lat, e.latlng.lng]) },
  })
  return null
}

// Map marker for selected location (uses a bare divIcon)
function PickedMarker({ pos }) {
  const map = useMap()
  useEffect(() => {
    if (!pos) return
    const L = window.L || (window.leaflet)
  }, [pos])
  return null
}

const initial = {
  patient_name: '', patient_age: '', patient_gender: 'male',
  phone: '',
  location_address: '',
  chief_complaint: '',
  pulse_rate: '', blood_pressure_systolic: '', blood_pressure_diastolic: '',
  respiratory_rate: '', spo2: '', gcs_score: '',
  symptoms: [],
  inferred_patient_type: '',
}

export default function EmergencyForm() {
  const nav = useNavigate()
  const toast = useUiStore(s => s.toast)
  const [form, setForm] = useState(initial)
  const [pos, setPos] = useState([19.0760, 72.8777])
  const [submitting, setSubmitting] = useState(false)

  // Live AI triage
  const [triage, setTriage] = useState(null)
  const [triageBusy, setTriageBusy] = useState(false)
  const debounceRef = useRef(null)

  // LLM transcript extraction
  const [transcript, setTranscript] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractMeta, setExtractMeta] = useState(null)

  const triagePayload = useMemo(() => ({
    age: parseInt(form.patient_age) || 40,
    gender: form.patient_gender,
    pulse_rate: form.pulse_rate ? parseInt(form.pulse_rate) : null,
    blood_pressure_systolic: form.blood_pressure_systolic ? parseInt(form.blood_pressure_systolic) : null,
    blood_pressure_diastolic: form.blood_pressure_diastolic ? parseInt(form.blood_pressure_diastolic) : null,
    respiratory_rate: form.respiratory_rate ? parseInt(form.respiratory_rate) : null,
    spo2: form.spo2 ? parseFloat(form.spo2) : null,
    gcs_score: form.gcs_score ? parseInt(form.gcs_score) : null,
    symptoms: form.symptoms,
  }), [form])

  // Debounced live triage call
  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (form.symptoms.length === 0 && !form.pulse_rate && !form.spo2) {
      setTriage(null); return
    }
    debounceRef.current = setTimeout(async () => {
      setTriageBusy(true)
      try {
        // strip null fields the backend doesn't want
        const clean = Object.fromEntries(
          Object.entries(triagePayload).filter(([, v]) => v !== null)
        )
        const t = await aiApi.triage(clean)
        setTriage(t)
      } catch {
        setTriage(null)
      } finally { setTriageBusy(false) }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [triagePayload])

  const toggleSymptom = (s) => {
    setForm(f => ({ ...f,
      symptoms: f.symptoms.includes(s) ? f.symptoms.filter(x => x !== s) : [...f.symptoms, s]
    }))
  }

  // Parse a free-text caller transcript into form fields. Existing user input
  // always wins — extracted values only fill blanks.
  async function extractFromTranscript() {
    if (!transcript.trim()) return
    setExtracting(true)
    try {
      const resp = await aiApi.extract(transcript.trim())
      const x = resp.extracted || {}
      const fill = (cur, val) => (cur !== '' && cur !== undefined && cur !== null) ? cur : (val ?? '')
      setForm(f => ({
        ...f,
        patient_age:               fill(f.patient_age, x.patient_age),
        patient_gender:            f.patient_gender !== 'male' ? f.patient_gender : (x.patient_gender || f.patient_gender),
        pulse_rate:                fill(f.pulse_rate, x.pulse_rate),
        blood_pressure_systolic:   fill(f.blood_pressure_systolic, x.blood_pressure_systolic),
        blood_pressure_diastolic:  fill(f.blood_pressure_diastolic, x.blood_pressure_diastolic),
        respiratory_rate:          fill(f.respiratory_rate, x.respiratory_rate),
        spo2:                      fill(f.spo2, x.spo2),
        gcs_score:                 fill(f.gcs_score, x.gcs_score),
        chief_complaint:           f.chief_complaint || x.chief_complaint || '',
        location_address:          f.location_address || x.location_hint || '',
        symptoms:                  Array.from(new Set([...f.symptoms, ...(x.symptoms || [])])),
        inferred_patient_type:     x.patient_type || f.inferred_patient_type,
      }))
      setExtractMeta({
        provider: resp.provider_used,
        latency: resp.latency_ms,
        used_fallback: resp.used_fallback,
        language: x.language_detected,
        severity_hint: x.severity_hint,
        patient_type: x.patient_type,
        error: resp.error,
      })
      const tag = resp.used_fallback ? 'heuristic fallback' : `via ${resp.provider_used}`
      toast(`Transcript parsed (${tag})`, resp.used_fallback ? 'info' : 'success')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Extraction failed', 'critical')
    } finally {
      setExtracting(false)
    }
  }

  async function submit(e, alsoDispatch = false) {
    e?.preventDefault()
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        patient_age:  form.patient_age ? parseInt(form.patient_age) : undefined,
        pulse_rate: form.pulse_rate ? parseInt(form.pulse_rate) : undefined,
        blood_pressure_systolic:  form.blood_pressure_systolic ? parseInt(form.blood_pressure_systolic) : undefined,
        blood_pressure_diastolic: form.blood_pressure_diastolic ? parseInt(form.blood_pressure_diastolic) : undefined,
        respiratory_rate: form.respiratory_rate ? parseInt(form.respiratory_rate) : undefined,
        spo2: form.spo2 ? parseFloat(form.spo2) : undefined,
        gcs_score: form.gcs_score ? parseInt(form.gcs_score) : undefined,
        location_lat: pos[0], location_lng: pos[1],
      }
      // strip undefineds + empty strings for cleanliness
      Object.keys(payload).forEach(k => {
        if (payload[k] === undefined || payload[k] === '') delete payload[k]
      })
      const e1 = await emergenciesApi.create(payload)
      toast(`Emergency #${e1.id} created`, 'success')
      if (alsoDispatch) {
        const plan = await emergenciesApi.dispatch(e1.id)
        toast(`SEV-${plan.severity_level} dispatched: ${plan.ambulance_registration} → ${plan.hospital_name.slice(0,28)}`, 'success', 7000)
      }
      nav('/dashboard')
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to create emergency', 'critical')
    } finally { setSubmitting(false) }
  }

  return (
    <div className="h-full flex">
      {/* ── Form ─────────────────────────────── */}
      <div className="w-[520px] shrink-0 border-r border-line/60 bg-ink-900/40 backdrop-blur overflow-y-auto">
        <form className="p-6 space-y-6" onSubmit={(e) => submit(e, false)}>
          <div>
            <div className="h-eyebrow mb-2">Caller intake</div>
            <h1 className="text-2xl font-bold">Report Emergency</h1>
            <p className="text-sm text-slate-400 mt-1">Click on the map to set the incident location. The AI will triage in real time as you fill vitals and symptoms.</p>
          </div>

          {/* Caller transcript -> auto-fill */}
          <Section title="Caller transcript" icon={MessageSquareText}>
            <div className="text-[10px] text-slate-500 mb-1.5">
              Type or paste what the caller is saying — English, Hindi, or Marathi. The
              AI extracts vitals, symptoms, and a patient-type hint into the form below.
            </div>
            <textarea
              className="field min-h-[80px] resize-y font-normal leading-relaxed"
              value={transcript}
              onChange={e => setTranscript(e.target.value)}
              placeholder="e.g. 60yo male, severe chest pain past 25 min, sweating, near gateway of india"
            />
            <div className="flex items-center gap-2 mt-2">
              <button
                type="button"
                onClick={extractFromTranscript}
                disabled={extracting || !transcript.trim()}
                className="btn-ghost flex-1 disabled:opacity-40"
              >
                {extracting
                  ? <><Loader2 className="w-4 h-4 animate-spin"/> Parsing…</>
                  : <><Wand2 className="w-4 h-4"/> Auto-fill from transcript</>}
              </button>
              {transcript && (
                <button
                  type="button"
                  onClick={() => { setTranscript(''); setExtractMeta(null) }}
                  className="btn-ghost px-3 text-slate-400 text-xs"
                >Clear</button>
              )}
            </div>
            {extractMeta && (
              <div className={`mt-2 p-2 rounded border text-[10px] font-mono leading-relaxed
                  ${extractMeta.used_fallback
                    ? 'bg-amber-500/5 border-amber-500/30 text-amber-300'
                    : 'bg-emerald-500/5 border-emerald-500/30 text-emerald-300'}`}>
                <div className="flex items-center justify-between mb-0.5">
                  <span>provider: {extractMeta.provider || '—'}</span>
                  <span>{extractMeta.latency ? `${extractMeta.latency}ms` : ''}</span>
                </div>
                <div className="text-slate-300/80">
                  {extractMeta.language && <>lang={extractMeta.language} · </>}
                  {extractMeta.patient_type && <>type={extractMeta.patient_type} · </>}
                  {extractMeta.severity_hint && <>sev hint={extractMeta.severity_hint}</>}
                </div>
                {extractMeta.used_fallback && (
                  <div className="mt-1 text-amber-200/70">
                    Heuristic mode — set GROQ_API_KEY in .env for full LLM extraction.
                  </div>
                )}
              </div>
            )}
          </Section>

          {/* Live triage banner */}
          <div className={`card p-3 transition-all relative overflow-hidden ${
              triage?.severity_level === 1 ? 'shadow-glow-red border-sig-critical/50' :
              triage?.severity_level === 2 ? 'border-sig-serious/50' :
              'border-line/60'
            }`}>
            <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400 mb-1.5">
              <Sparkles className="w-3 h-3"/> Live AI triage
              {triageBusy && <Loader2 className="w-3 h-3 animate-spin"/>}
            </div>
            {triage ? (
              <div className="flex items-center justify-between gap-3">
                <SeverityPill level={triage.severity_level} confidence={triage.confidence}/>
                <span className="text-[10px] font-mono text-slate-500">
                  {triage.used_fallback ? 'heuristic' : 'model'}
                </span>
              </div>
            ) : (
              <div className="text-sm text-slate-500">— enter vitals / symptoms —</div>
            )}
          </div>

          {/* Location */}
          <Section title="Location" icon={MapPin}>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Latitude">
                <input className="field font-mono" value={pos[0].toFixed(5)} readOnly/>
              </Field>
              <Field label="Longitude">
                <input className="field font-mono" value={pos[1].toFixed(5)} readOnly/>
              </Field>
            </div>
            <Field label="Address" className="mt-3">
              <input className="field" value={form.location_address}
                     onChange={e => setForm({ ...form, location_address: e.target.value })}
                     placeholder="e.g. MG Road, Mumbai"/>
            </Field>
          </Section>

          {/* Patient */}
          <Section title="Patient">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name">
                <input className="field" value={form.patient_name}
                       onChange={e => setForm({ ...form, patient_name: e.target.value })}/>
              </Field>
              <Field label="Phone">
                <input className="field font-mono" value={form.phone}
                       onChange={e => setForm({ ...form, phone: e.target.value })}/>
              </Field>
              <Field label="Age">
                <input type="number" className="field font-mono" value={form.patient_age}
                       onChange={e => setForm({ ...form, patient_age: e.target.value })}/>
              </Field>
              <Field label="Sex">
                <select className="field" value={form.patient_gender}
                        onChange={e => setForm({ ...form, patient_gender: e.target.value })}>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </Field>
            </div>
            <Field label="Chief complaint" className="mt-3">
              <input className="field" value={form.chief_complaint}
                     onChange={e => setForm({ ...form, chief_complaint: e.target.value })}
                     placeholder="e.g. Crushing chest pain, sudden onset"/>
            </Field>
          </Section>

          {/* Vitals */}
          <Section title="Vitals" icon={Activity}>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Pulse"><input type="number" className="field font-mono"
                value={form.pulse_rate} onChange={e => setForm({ ...form, pulse_rate: e.target.value })}/></Field>
              <Field label="SpO₂"><input type="number" className="field font-mono"
                value={form.spo2} onChange={e => setForm({ ...form, spo2: e.target.value })}/></Field>
              <Field label="GCS"><input type="number" className="field font-mono"
                value={form.gcs_score} onChange={e => setForm({ ...form, gcs_score: e.target.value })}/></Field>
              <Field label="Resp rate"><input type="number" className="field font-mono"
                value={form.respiratory_rate} onChange={e => setForm({ ...form, respiratory_rate: e.target.value })}/></Field>
              <Field label="BP sys"><input type="number" className="field font-mono"
                value={form.blood_pressure_systolic} onChange={e => setForm({ ...form, blood_pressure_systolic: e.target.value })}/></Field>
              <Field label="BP dia"><input type="number" className="field font-mono"
                value={form.blood_pressure_diastolic} onChange={e => setForm({ ...form, blood_pressure_diastolic: e.target.value })}/></Field>
            </div>
          </Section>

          {/* Symptoms */}
          <Section title="Symptoms">
            <div className="space-y-3">
              {Object.entries(SYMPTOMS_GROUPS).map(([group, syms]) => (
                <div key={group}>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">{group}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {syms.map(s => {
                      const on = form.symptoms.includes(s)
                      return (
                        <button key={s} type="button" onClick={() => toggleSymptom(s)}
                          className={`px-2 py-1 text-[11px] font-mono rounded border transition-all
                            ${on
                              ? 'bg-sig-critical/15 border-sig-critical/50 text-red-200'
                              : 'bg-ink-700/50 border-line text-slate-400 hover:border-cyan-400/40 hover:text-slate-200'}`}>
                          {s.replaceAll('_',' ')}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {/* Actions */}
          <div className="flex gap-2 pt-2 border-t border-line/40">
            <button type="submit" disabled={submitting} className="btn-ghost flex-1">
              Create only
            </button>
            <button type="button" onClick={(e) => submit(e, true)} disabled={submitting}
                    className="btn-danger flex-1">
              <Send className="w-4 h-4"/>{submitting ? 'Working…' : 'Create + Dispatch'}
            </button>
          </div>
        </form>
      </div>

      {/* ── Map ──────────────────────────────── */}
      <div className="flex-1 relative">
        <MapView
          showAmbulances showHospitals
          showEmergencies={false}
          showRoutes={false}
        >
          <ClickToPlace onPick={setPos}/>
        </MapView>
        <div className="absolute top-4 right-4 card p-3 z-[400] text-xs font-mono">
          <div className="text-slate-400 mb-1 uppercase tracking-wider">Selected</div>
          <div>{pos[0].toFixed(4)}, {pos[1].toFixed(4)}</div>
          <div className="text-slate-500 text-[10px] mt-1">Click anywhere on the map</div>
        </div>
      </div>
    </div>
  )
}

// ── Tiny field/section helpers ──
function Section({ title, icon: Icon, children }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">
        {Icon && <Icon className="w-3 h-3"/>}{title}
      </div>
      {children}
    </div>
  )
}

function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className="field-label">{label}</label>
      {children}
    </div>
  )
}
