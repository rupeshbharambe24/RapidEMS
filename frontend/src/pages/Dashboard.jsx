import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Truck, Building2, AlertTriangle, Activity, Bed, TimerReset, Plus, Send, Wand2, Loader2, X, Sparkles } from 'lucide-react'

import MapView from '../components/MapView.jsx'
import KPICard from '../components/KPICard.jsx'
import CopilotPanel from '../components/CopilotPanel.jsx'
import { AmbStatusPill, EmergencyStatusPill, SeverityPill } from '../components/StatusBadge.jsx'

import { analyticsApi, emergenciesApi, dispatchesApi } from '../api/client.js'
import { useAmbulancesStore } from '../store/ambulances.js'
import { useDronesStore } from '../store/drones.js'
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
  const fetchDrones = useDronesStore(s => s.fetch)
  const toast       = useUiStore(s => s.toast)

  const [kpis, setKpis] = useState(null)
  const [flyTo, setFlyTo] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [copilotOpen, setCopilotOpen] = useState(false)

  // Global '/' shortcut to open the copilot. Skips when the user is typing
  // in an input / textarea so it doesn't hijack form fields.
  useEffect(() => {
    function onKey(e) {
      if (e.key !== '/') return
      const tag = (e.target?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return
      e.preventDefault()
      setCopilotOpen(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Initial load
  useEffect(() => {
    fetchAmbs(); fetchHosps(); fetchEmers({ limit: 50 }); fetchActive()
    fetchDrones()
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

  // Hungarian multi-emergency optimisation. Preview first, then on confirm
  // execute and dispatch every pair.
  const [optPreview, setOptPreview] = useState(null)
  const [optBusy, setOptBusy] = useState(false)
  async function previewOptimize() {
    setOptBusy(true)
    try {
      const r = await dispatchesApi.optimize(false)
      if (r.proposals.length === 0) {
        toast('Nothing to optimize — no eligible pending calls.', 'info')
        return
      }
      setOptPreview(r)
    } catch (e) {
      toast(e?.response?.data?.detail || 'Optimize failed', 'critical')
    } finally { setOptBusy(false) }
  }
  async function executeOptimize() {
    setOptBusy(true)
    try {
      const r = await dispatchesApi.optimize(true)
      toast(`Dispatched ${r.dispatched_plans.length} call(s) by global optimum.`, 'success', 7000)
      setOptPreview(null)
      fetchEmers({ limit: 50 }); fetchAmbs(); fetchActive(); refreshKpis()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Optimize execute failed', 'critical')
    } finally { setOptBusy(false) }
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
            <div className="flex items-center gap-1">
              {pending.length >= 2 && (
                <button onClick={previewOptimize} disabled={optBusy}
                  title="Hungarian-algorithm global optimum"
                  className="btn-ghost !px-2 !py-1 text-xs disabled:opacity-40">
                  {optBusy
                    ? <Loader2 className="w-3 h-3 animate-spin"/>
                    : <Wand2 className="w-3 h-3"/>}
                  optimize
                </button>
              )}
              <button onClick={() => nav('/intake')}
                className="btn-primary !px-2.5 !py-1 text-xs">
                <Plus className="w-3 h-3"/> New
              </button>
            </div>
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

      {/* Copilot launcher — bottom-right, always visible */}
      <button
        onClick={() => setCopilotOpen(true)}
        className="fixed bottom-5 right-5 z-30 px-3.5 py-2.5 rounded-full
                   bg-amber-400/15 hover:bg-amber-400/25 border border-amber-400/40
                   text-amber-200 shadow-2xl backdrop-blur transition-all
                   flex items-center gap-2"
        title="Ask the copilot (/)"
      >
        <Sparkles className="w-4 h-4"/>
        <span className="text-xs font-mono uppercase tracking-wider hidden sm:inline">copilot</span>
        <kbd className="hidden sm:inline-flex items-center px-1 py-0.5 rounded border border-amber-400/30 text-[10px] font-mono">/</kbd>
      </button>
      <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)}/>

      {/* Multi-emergency optimisation preview */}
      {optPreview && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm p-4">
          <div className="card p-6 w-[560px] max-w-[94vw] max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="h-eyebrow mb-1">Hungarian optimum</div>
                <h3 className="text-lg font-bold">Multi-emergency assignment</h3>
              </div>
              <button onClick={() => setOptPreview(null)}
                      className="text-slate-400 hover:text-slate-100">
                <X className="w-4 h-4"/>
              </button>
            </div>
            <p className="text-sm text-slate-400 mb-4">
              Cost-minimising assignment over {optPreview.proposals.length} pending call(s).
              Dispatches in this order will give the best collective response time
              (severity-weighted).
            </p>
            <div className="divide-y divide-line/30">
              {optPreview.proposals.map(p => (
                <div key={p.emergency_id} className="py-2 flex items-center gap-3 text-sm">
                  <div className={`w-1.5 h-8 rounded-full shrink-0 ${
                    p.severity_level === 1 ? 'bg-sig-critical' :
                    p.severity_level === 2 ? 'bg-sig-serious' :
                    p.severity_level === 3 ? 'bg-sig-moderate' :
                    'bg-cyan-400'}`}/>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-xs">
                      Emergency #{p.emergency_id} <span className="text-slate-500">SEV-{p.severity_level}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      via {p.road_provider}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-sm">{p.ambulance_registration}</div>
                    <div className="text-[10px] text-slate-400">ETA {p.predicted_eta_minutes}m</div>
                  </div>
                </div>
              ))}
            </div>
            {optPreview.unassigned_emergency_ids.length > 0 && (
              <div className="mt-3 text-xs text-amber-300">
                {optPreview.unassigned_emergency_ids.length} call(s) couldn't be paired
                — no eligible ambulance type available right now.
              </div>
            )}
            <div className="flex gap-2 mt-5 pt-4 border-t border-line/30">
              <button onClick={executeOptimize} disabled={optBusy}
                      className="btn-danger flex-1">
                {optBusy
                  ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin"/>dispatching…</span>
                  : `Dispatch all ${optPreview.proposals.length}`}
              </button>
              <button onClick={() => setOptPreview(null)}
                      className="btn-ghost px-4">cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
