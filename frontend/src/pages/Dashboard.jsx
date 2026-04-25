import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Truck, Building2, AlertTriangle, Activity, Bed, TimerReset, Plus, Send } from 'lucide-react'

import MapView from '../components/MapView.jsx'
import KPICard from '../components/KPICard.jsx'
import { AmbStatusPill, EmergencyStatusPill, SeverityPill } from '../components/StatusBadge.jsx'

import { analyticsApi, emergenciesApi } from '../api/client.js'
import { useAmbulancesStore } from '../store/ambulances.js'
import { useEmergenciesStore } from '../store/emergencies.js'
import { useHospitalsStore } from '../store/hospitals.js'
import { useDispatchesStore } from '../store/dispatches.js'
import { useUiStore } from '../store/ui.js'
import { fmtMinutes, fmtRelative } from '../utils/format.js'

export default function Dashboard() {
  const nav = useNavigate()
  const ambulances  = useAmbulancesStore(s => s.items)
  const fetchAmbs   = useAmbulancesStore(s => s.fetch)
  const emergencies = useEmergenciesStore(s => s.items)
  const fetchEmers  = useEmergenciesStore(s => s.fetch)
  const fetchHosps  = useHospitalsStore(s => s.fetch)
  const active      = useDispatchesStore(s => s.active)
  const fetchActive = useDispatchesStore(s => s.fetchActive)
  const toast       = useUiStore(s => s.toast)

  const [kpis, setKpis] = useState(null)
  const [flyTo, setFlyTo] = useState(null)
  const [busyId, setBusyId] = useState(null)

  // Initial load
  useEffect(() => {
    fetchAmbs(); fetchHosps(); fetchEmers({ limit: 50 }); fetchActive()
    refreshKpis()
  }, [])

  // Light polling fallback (in case socket drops; cheap calls)
  useEffect(() => {
    const t = setInterval(() => {
      fetchAmbs(); fetchEmers({ limit: 50 }); fetchActive(); refreshKpis()
    }, 8000)
    return () => clearInterval(t)
  }, [])

  async function refreshKpis() {
    try { setKpis(await analyticsApi.kpis()) } catch {}
  }

  async function dispatchOne(id) {
    setBusyId(id)
    try {
      const plan = await emergenciesApi.dispatch(id)
      toast(`SEV-${plan.severity_level} → ${plan.ambulance_registration} → ${plan.hospital_name.slice(0,28)}`, 'success')
      fetchEmers({ limit: 50 }); fetchAmbs(); fetchActive(); refreshKpis()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Dispatch failed', 'critical')
    } finally { setBusyId(null) }
  }

  const pending = emergencies.filter(e => e.status === 'pending')

  return (
    <div className="h-full flex">
      {/* ── Left rail: KPIs + pending queue ─────────────────────── */}
      <div className="w-80 shrink-0 border-r border-line/60 bg-ink-900/40 backdrop-blur flex flex-col overflow-hidden">
        {/* KPIs */}
        <div className="p-4 grid grid-cols-2 gap-3">
          <KPICard label="Active" value={kpis?.active_dispatches ?? '—'} accent="cyan" icon={Activity}
                   hint={`${kpis?.busy_ambulances ?? 0} units busy`}/>
          <KPICard label="Pending" value={kpis?.pending_emergencies ?? '—'} accent={pending.length > 0 ? 'red' : 'slate'}
                   icon={AlertTriangle}/>
          <KPICard label="Available" value={kpis?.available_ambulances ?? '—'} accent="emerald" icon={Truck}/>
          <KPICard label="Diversion" value={kpis?.hospitals_on_diversion ?? '—'}
                   accent={kpis?.hospitals_on_diversion > 0 ? 'amber' : 'slate'} icon={Building2}/>
          <KPICard label="24h Calls" value={kpis?.total_emergencies_24h ?? '—'} accent="slate" icon={TimerReset}/>
          <KPICard label="Avg Sev" value={kpis?.avg_severity?.toFixed(1) ?? '—'} accent="slate" icon={Bed}/>
        </div>

        {/* Pending emergencies */}
        <div className="px-4 pt-2 pb-3">
          <div className="flex items-center justify-between mb-2">
            <div className="h-eyebrow">Pending intake</div>
            <button onClick={() => nav('/intake')}
              className="btn-primary !px-2.5 !py-1 text-xs">
              <Plus className="w-3 h-3"/> New
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2">
          {pending.length === 0 && (
            <div className="text-center py-8 text-slate-500 text-sm">
              <div className="text-3xl mb-2 opacity-40">∎</div>
              No pending calls
            </div>
          )}
          {pending.map(e => (
            <div key={e.id}
              className="card card-hover p-3 cursor-pointer"
              onClick={() => setFlyTo([e.location_lat, e.location_lng])}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">#{e.id} • {fmtRelative(e.created_at)}</div>
                  <div className="text-sm font-medium truncate mt-0.5">{e.chief_complaint || '— no complaint —'}</div>
                  <div className="text-xs text-slate-400 truncate">{e.location_address || `${e.location_lat?.toFixed(4)}, ${e.location_lng?.toFixed(4)}`}</div>
                </div>
              </div>
              {e.predicted_severity ? (
                <div className="mt-2"><SeverityPill level={e.predicted_severity} confidence={e.severity_confidence}/></div>
              ) : (
                <div className="mt-2 text-[10px] font-mono uppercase tracking-wider text-slate-500">awaiting triage</div>
              )}
              <button
                onClick={(ev) => { ev.stopPropagation(); dispatchOne(e.id) }}
                disabled={busyId === e.id}
                className="btn-danger w-full mt-3 disabled:opacity-50">
                <Send className="w-3.5 h-3.5"/>
                {busyId === e.id ? 'Dispatching…' : 'Dispatch now'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── Center: map ─────────────────────────────────────────── */}
      <div className="flex-1 relative">
        <MapView flyTo={flyTo}/>
        {/* Bottom-left legend */}
        <div className="absolute bottom-4 left-4 card p-3 z-[400] text-[11px] font-mono uppercase tracking-wider">
          <div className="text-slate-400 mb-1.5">Legend</div>
          <div className="space-y-1">
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-sig-minimal"/>Available</div>
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-sig-moderate"/>En route</div>
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-sig-minor"/>Transporting</div>
            <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-sig-critical"/>Emergency</div>
          </div>
        </div>
      </div>

      {/* ── Right rail: active dispatches ───────────────────────── */}
      <div className="w-80 shrink-0 border-l border-line/60 bg-ink-900/40 backdrop-blur flex flex-col overflow-hidden">
        <div className="p-4 pb-2">
          <div className="h-eyebrow">Active dispatches</div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2">
          {active.length === 0 && (
            <div className="text-center py-8 text-slate-500 text-sm">
              <div className="text-3xl mb-2 opacity-40">○</div>
              No active dispatches
            </div>
          )}
          {active.map(d => {
            const amb = ambulances.find(a => a.id === d.ambulance_id)
            return (
              <div key={d.id} className="card card-hover p-3"
                   onClick={() => amb && setFlyTo([amb.current_lat, amb.current_lng])}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="font-mono text-sm font-semibold">{amb?.registration_number || `AMB-${d.ambulance_id}`}</div>
                  <span className="font-mono text-[10px] text-slate-500">#{d.id}</span>
                </div>
                <AmbStatusPill status={d.status}/>
                <div className="grid grid-cols-3 gap-2 mt-2.5 text-[11px] font-mono">
                  <div>
                    <div className="text-slate-500 uppercase tracking-wider">ETA</div>
                    <div className="text-slate-200">{fmtMinutes(d.predicted_eta_seconds / 60)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase tracking-wider">Dist</div>
                    <div className="text-slate-200">{(d.distance_meters / 1000).toFixed(1)}km</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase tracking-wider">Score</div>
                    <div className="text-slate-200">{(d.hospital_recommendation_score * 100).toFixed(0)}%</div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
