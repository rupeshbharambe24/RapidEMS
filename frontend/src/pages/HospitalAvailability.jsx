import { useEffect, useState } from 'react'
import { Building2, Save, AlertTriangle } from 'lucide-react'

import { hospitalsApi } from '../api/client.js'
import { useHospitalsStore } from '../store/hospitals.js'
import { useUiStore } from '../store/ui.js'

export default function HospitalAvailability() {
  const hospitals = useHospitalsStore(s => s.items)
  const fetchHosps = useHospitalsStore(s => s.fetch)
  const upsert = useHospitalsStore(s => s.upsert)
  const toast = useUiStore(s => s.toast)

  const [editId, setEditId] = useState(null)
  const [edits, setEdits]   = useState({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchHosps()
    const t = setInterval(() => fetchHosps(), 8000)
    return () => clearInterval(t)
  }, [])

  function startEdit(h) {
    setEditId(h.id)
    setEdits({
      available_beds_general:   h.available_beds_general,
      available_beds_icu:       h.available_beds_icu,
      available_beds_trauma:    h.available_beds_trauma,
      available_beds_pediatric: h.available_beds_pediatric,
      available_beds_burns:     h.available_beds_burns,
      er_wait_minutes:          h.er_wait_minutes,
      is_diversion:             h.is_diversion,
    })
  }

  async function saveEdits() {
    setSaving(true)
    try {
      const updated = await hospitalsApi.updateBeds(editId, edits)
      upsert(updated)
      toast('Hospital updated', 'success')
      setEditId(null); setEdits({})
    } catch (e) {
      toast(e?.response?.data?.detail || 'Update failed', 'critical')
    } finally { setSaving(false) }
  }

  const onDiversion = hospitals.filter(h => h.is_diversion).length

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="h-eyebrow mb-1">Facility status</div>
          <h1 className="text-2xl font-bold">Hospital Availability</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {hospitals.length} active facilities {onDiversion > 0 && (
              <span className="text-sig-critical font-mono">▸ {onDiversion} on diversion</span>
            )}
          </p>
        </div>
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {hospitals.map(h => (
          <div key={h.id}
            className={`card p-5 transition-all ${h.is_diversion ? 'border-sig-critical/60 shadow-glow-red' : 'card-hover'}`}>
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <Building2 className="w-4 h-4 text-cyan-400 shrink-0"/>
                  <h3 className="font-semibold truncate">{h.name}</h3>
                </div>
                <div className="text-xs text-slate-400 truncate">{h.address}</div>
                {h.is_diversion && (
                  <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-mono uppercase text-sig-critical">
                    <AlertTriangle className="w-3 h-3"/>On Diversion
                  </div>
                )}
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Quality</div>
                <div className="font-mono text-lg">{'★'.repeat(h.quality_rating)}<span className="text-slate-700">{'★'.repeat(5 - h.quality_rating)}</span></div>
              </div>
            </div>

            {/* Specialties */}
            <div className="flex flex-wrap gap-1 mb-4">
              {(h.specialties || []).map(s => (
                <span key={s} className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-ink-700/70 border border-line text-slate-400 rounded">
                  {s}
                </span>
              ))}
            </div>

            {/* Bed grid */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <BedCell label="General"   avail={h.available_beds_general}   total={h.total_beds_general}/>
              <BedCell label="ICU"       avail={h.available_beds_icu}       total={h.total_beds_icu}/>
              <BedCell label="Trauma"    avail={h.available_beds_trauma}    total={h.total_beds_trauma}/>
              <BedCell label="Pediatric" avail={h.available_beds_pediatric} total={h.total_beds_pediatric}/>
              <BedCell label="Burns"     avail={h.available_beds_burns}     total={h.total_beds_burns}/>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5">ER wait</div>
                <div className="font-mono text-base tabular-nums">{h.er_wait_minutes}<span className="text-slate-500 text-xs ml-0.5">m</span></div>
              </div>
            </div>

            {/* Edit form */}
            {editId === h.id ? (
              <div className="mt-4 pt-4 border-t border-line/50 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  {['available_beds_general','available_beds_icu','available_beds_trauma','available_beds_pediatric','available_beds_burns','er_wait_minutes'].map(key => (
                    <div key={key}>
                      <label className="text-[9px] font-mono uppercase tracking-wider text-slate-500 block">
                        {key.replace('available_beds_','').replace('er_wait_minutes','wait')}
                      </label>
                      <input type="number"
                        className="field font-mono !py-1 !text-xs"
                        value={edits[key] ?? ''}
                        onChange={e => setEdits({...edits, [key]: parseInt(e.target.value) || 0})}/>
                    </div>
                  ))}
                </div>
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={!!edits.is_diversion}
                         onChange={e => setEdits({...edits, is_diversion: e.target.checked})}/>
                  <span>On Diversion</span>
                </label>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => { setEditId(null); setEdits({}) }} className="btn-ghost flex-1 !text-xs !py-1.5">Cancel</button>
                  <button onClick={saveEdits} disabled={saving} className="btn-primary flex-1 !text-xs !py-1.5">
                    <Save className="w-3 h-3"/>{saving ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            ) : (
              <button onClick={() => startEdit(h)} className="btn-ghost w-full mt-4 !py-1.5 !text-xs">
                Update beds & wait
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function BedCell({ label, avail, total }) {
  const pct = total > 0 ? (avail / total) * 100 : 0
  const color = pct > 30 ? '#10b981' : pct > 10 ? '#f59e0b' : '#ef4444'
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-base tabular-nums" style={{ color }}>{avail}</span>
        <span className="text-xs text-slate-500 font-mono">/ {total}</span>
      </div>
      <div className="h-1 bg-ink-700 rounded mt-1 overflow-hidden">
        <div className="h-full transition-all" style={{ width: `${pct}%`, background: color }}/>
      </div>
    </div>
  )
}
