import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import { useEffect } from 'react'

import { useAmbulancesStore } from '../store/ambulances.js'
import { useEmergenciesStore } from '../store/emergencies.js'
import { useHospitalsStore } from '../store/hospitals.js'
import { useDispatchesStore } from '../store/dispatches.js'
import { ambulanceIcon, hospitalIcon, emergencyIcon } from '../utils/icons.js'
import { AmbStatusPill, SeverityPill } from './StatusBadge.jsx'
import { fmtKm, fmtRelative } from '../utils/format.js'

const DEFAULT_CENTER = [19.0760, 72.8777]   // Mumbai (matches backend seed)
const DEFAULT_ZOOM   = 12

// ── Helper to fly the map to a target when it changes ──
function FlyTo({ center, zoom }) {
  const map = useMap()
  useEffect(() => {
    if (center) map.flyTo(center, zoom ?? map.getZoom(), { duration: 0.7 })
  }, [center?.[0], center?.[1], zoom])
  return null
}

export default function MapView({
  center      = DEFAULT_CENTER,
  zoom        = DEFAULT_ZOOM,
  showAmbulances = true,
  showHospitals  = true,
  showEmergencies= true,
  showRoutes     = true,
  children,
  flyTo        = null,
  className    = '',
}) {
  const ambulances  = useAmbulancesStore(s => s.items)
  const hospitals   = useHospitalsStore(s => s.items)
  const emergencies = useEmergenciesStore(s => s.items).filter(e => e.status !== 'resolved' && e.status !== 'cancelled')
  const active      = useDispatchesStore(s => s.active)

  return (
    <div className={`relative w-full h-full ${className}`}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom
        className="w-full h-full"
        zoomControl={true}
        attributionControl={true}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; OpenStreetMap contributors'
          maxZoom={19}
        />

        <FlyTo center={flyTo} zoom={flyTo ? 14 : null} />

        {/* Hospitals */}
        {showHospitals && hospitals.map(h => (
          <Marker key={`h${h.id}`} position={[h.lat, h.lng]}
                  icon={hospitalIcon(h.available_beds_general + h.available_beds_icu)}>
            <Popup>
              <div className="font-semibold mb-1">{h.name}</div>
              <div className="text-xs text-slate-300 mb-2">{h.address}</div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
                <span className="text-slate-400">General</span>
                <span>{h.available_beds_general}/{h.total_beds_general}</span>
                <span className="text-slate-400">ICU</span>
                <span>{h.available_beds_icu}/{h.total_beds_icu}</span>
                <span className="text-slate-400">Trauma</span>
                <span>{h.available_beds_trauma}/{h.total_beds_trauma}</span>
                <span className="text-slate-400">ER wait</span>
                <span>{h.er_wait_minutes}m</span>
              </div>
              {h.is_diversion && (
                <div className="mt-2 text-xs text-sig-critical font-semibold">⚠ ON DIVERSION</div>
              )}
            </Popup>
          </Marker>
        ))}

        {/* Ambulances */}
        {showAmbulances && ambulances
          .filter(a => a.current_lat != null && a.current_lng != null)
          .map(a => (
            <Marker key={`a${a.id}`} position={[a.current_lat, a.current_lng]}
                    icon={ambulanceIcon(a.status)}>
              <Popup>
                <div className="font-mono font-semibold mb-1">{a.registration_number}</div>
                <div className="mb-1.5"><AmbStatusPill status={a.status} /></div>
                <div className="text-xs text-slate-300">
                  Type: <span className="font-mono uppercase">{a.ambulance_type}</span>
                </div>
                <div className="text-xs text-slate-300">Crew: {a.paramedic_name}</div>
                {a.last_gps_update && (
                  <div className="text-xs text-slate-500 mt-1">
                    Updated {fmtRelative(a.last_gps_update)}
                  </div>
                )}
              </Popup>
            </Marker>
          ))}

        {/* Emergencies */}
        {showEmergencies && emergencies.map(e => (
          <Marker key={`e${e.id}`} position={[e.location_lat, e.location_lng]}
                  icon={emergencyIcon(e.predicted_severity || 3)}>
            <Popup>
              <div className="font-mono text-xs text-slate-400 mb-1">EMERGENCY #{e.id}</div>
              {e.predicted_severity && (
                <div className="mb-2">
                  <SeverityPill level={e.predicted_severity} confidence={e.severity_confidence}/>
                </div>
              )}
              <div className="text-sm font-semibold mb-1">{e.chief_complaint || '—'}</div>
              <div className="text-xs text-slate-300">{e.location_address}</div>
              {e.symptoms?.length > 0 && (
                <div className="mt-1.5 text-xs">
                  {e.symptoms.slice(0, 4).map(s => (
                    <span key={s} className="inline-block bg-ink-700 text-slate-300 rounded px-1.5 py-0.5 mr-1 mb-1 text-[10px] font-mono">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </Popup>
          </Marker>
        ))}

        {/* Active routes — straight polylines from ambulance to emergency */}
        {showRoutes && active.map(d => {
          const amb  = ambulances.find(a => a.id === d.ambulance_id)
          const emer = emergencies.find(e => e.id === d.emergency_id)
          const hosp = hospitals.find(h => h.id === d.hospital_id)
          if (!amb || amb.current_lat == null) return null
          // Decide endpoints based on status
          const enRoute      = ['dispatched', 'en_route'].includes(d.status)
          const transporting = d.status === 'transporting'
          if (enRoute && emer) {
            return (
              <Polyline key={`r${d.id}-eo`}
                positions={[[amb.current_lat, amb.current_lng],
                            [emer.location_lat, emer.location_lng]]}
                pathOptions={{ color: '#f59e0b', weight: 3, dashArray: '4,8', opacity: 0.85 }}/>
            )
          }
          if (transporting && hosp) {
            return (
              <Polyline key={`r${d.id}-th`}
                positions={[[amb.current_lat, amb.current_lng],
                            [hosp.lat, hosp.lng]]}
                pathOptions={{ color: '#06b6d4', weight: 3, dashArray: '4,8', opacity: 0.85 }}/>
            )
          }
          return null
        })}

        {children}
      </MapContainer>

      {/* Mission-control scanline overlay */}
      <div className="absolute inset-0 pointer-events-none scanlines"/>
    </div>
  )
}
