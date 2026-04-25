import { useEffect, useMemo, useState } from 'react'
import { Truck, Phone, Clock } from 'lucide-react'

import MapView from '../components/MapView.jsx'
import { AmbStatusPill } from '../components/StatusBadge.jsx'
import { useAmbulancesStore } from '../store/ambulances.js'
import { useDispatchesStore } from '../store/dispatches.js'
import { useHospitalsStore } from '../store/hospitals.js'
import { useEmergenciesStore } from '../store/emergencies.js'
import { fmtMinutes, fmtRelative } from '../utils/format.js'

const STATUS_TABS = [
  { key: 'all',          label: 'All' },
  { key: 'available',    label: 'Available' },
  { key: 'en_route',     label: 'En Route' },
  { key: 'on_scene',     label: 'On Scene' },
  { key: 'transporting', label: 'Transporting' },
]

export default function AmbulanceTracking() {
  const ambulances  = useAmbulancesStore(s => s.items)
  const fetchAmbs   = useAmbulancesStore(s => s.fetch)
  const fetchHosps  = useHospitalsStore(s => s.fetch)
  const fetchActive = useDispatchesStore(s => s.fetchActive)
  const fetchEmers  = useEmergenciesStore(s => s.fetch)
  const active      = useDispatchesStore(s => s.active)
  const hospitals   = useHospitalsStore(s => s.items)

  const [tab, setTab] = useState('all')
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    fetchAmbs(); fetchHosps(); fetchActive(); fetchEmers({ limit: 50 })
    const t = setInterval(() => { fetchAmbs(); fetchActive() }, 4000)
    return () => clearInterval(t)
  }, [])

  const filtered = useMemo(() => (
    tab === 'all' ? ambulances : ambulances.filter(a => a.status === tab)
  ), [tab, ambulances])

  const selected = ambulances.find(a => a.id === selectedId)
  const dispatch = selected && active.find(d => d.ambulance_id === selected.id)
  const dispatchHospital = dispatch && hospitals.find(h => h.id === dispatch.hospital_id)

  const flyTo = selected && selected.current_lat != null
    ? [selected.current_lat, selected.current_lng] : null

  return (
    <div className="h-full flex">
      {/* ── List ─────────────────────────────── */}
      <div className="w-96 shrink-0 border-r border-line/60 bg-ink-900/40 backdrop-blur flex flex-col">
        <div className="p-4 pb-3 border-b border-line/40">
          <div className="h-eyebrow mb-2">Fleet</div>
          <div className="flex gap-1 overflow-x-auto -mx-1 px-1">
            {STATUS_TABS.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`text-[11px] font-mono uppercase tracking-wider px-2.5 py-1.5 rounded whitespace-nowrap transition-all
                  ${tab === t.key
                    ? 'bg-cyan-400/15 text-cyan-300 border border-cyan-400/40'
                    : 'text-slate-400 hover:text-slate-200 border border-transparent'}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1.5">
          {filtered.length === 0 && (
            <div className="text-center py-12 text-slate-500 text-sm">No ambulances match.</div>
          )}
          {filtered.map(a => (
            <div key={a.id}
                 onClick={() => setSelectedId(a.id)}
                 className={`card cursor-pointer p-3 transition-all
                    ${selectedId === a.id ? 'border-cyan-400/60 bg-cyan-400/5' : 'card-hover'}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="font-mono font-semibold text-sm">{a.registration_number}</div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">{a.ambulance_type}</span>
              </div>
              <AmbStatusPill status={a.status}/>
              <div className="grid grid-cols-2 gap-x-3 mt-2 text-[11px] text-slate-400">
                <div className="truncate">{a.paramedic_name || '—'}</div>
                <div className="text-right font-mono">
                  {a.last_gps_update ? fmtRelative(a.last_gps_update) : '—'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Map ──────────────────────────────── */}
      <div className="flex-1 relative">
        <MapView
          flyTo={flyTo}
          showEmergencies={!!dispatch}
        />

        {/* Detail panel */}
        {selected && (
          <div className="absolute top-4 right-4 z-[400] card p-4 w-80 animate-fadeIn">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Unit</div>
                <div className="font-mono text-lg font-bold leading-none">{selected.registration_number}</div>
              </div>
              <Truck className="w-5 h-5 text-cyan-400"/>
            </div>
            <AmbStatusPill status={selected.status}/>

            <div className="mt-3 space-y-2 text-sm">
              <Row label="Type"  value={(selected.ambulance_type || '').toUpperCase()}/>
              <Row label="Crew"  value={selected.paramedic_name || '—'}/>
              <Row label="Cert"  value={selected.paramedic_certification || '—'}/>
              <Row label="Phone" icon={Phone} value={selected.paramedic_phone || '—'}/>
              <Row label="Depot" value={selected.home_station_name || '—'}/>
              <Row label="GPS"   icon={Clock} value={selected.last_gps_update ? fmtRelative(selected.last_gps_update) : '—'}/>
            </div>

            {dispatch && (
              <div className="mt-4 pt-4 border-t border-line/50">
                <div className="h-eyebrow mb-2">Active dispatch #{dispatch.id}</div>
                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                  <div>
                    <div className="text-slate-500 uppercase tracking-wider">ETA</div>
                    <div>{fmtMinutes(dispatch.predicted_eta_seconds / 60)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase tracking-wider">Distance</div>
                    <div>{(dispatch.distance_meters / 1000).toFixed(1)} km</div>
                  </div>
                </div>
                {dispatchHospital && (
                  <div className="mt-2 text-xs">
                    <span className="text-slate-500 uppercase tracking-wider font-mono text-[10px]">Destination ▸ </span>
                    {dispatchHospital.name}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value, icon: Icon }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 w-14 shrink-0">{label}</span>
      {Icon && <Icon className="w-3 h-3 text-slate-500"/>}
      <span className="text-slate-200 truncate">{value}</span>
    </div>
  )
}
