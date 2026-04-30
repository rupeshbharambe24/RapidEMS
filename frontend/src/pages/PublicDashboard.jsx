import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity, AlertTriangle, Building2, Truck, Bed, Hospital as HospitalIcon,
  Clock, MapPin, RefreshCw, ShieldOff, Heart,
} from 'lucide-react'

import { publicApi } from '../api/client.js'
import LangPicker from '../components/LangPicker.jsx'

const TICK_MS = 15000  // refresh cadence

export default function PublicDashboard() {
  const { t } = useTranslation()
  const [city, setCity] = useState(null)
  const [zones, setZones] = useState([])
  const [hospitals, setHospitals] = useState([])
  const [error, setError] = useState(null)
  const tickRef = useRef(null)

  async function refresh() {
    try {
      const [c, z, h] = await Promise.all([
        publicApi.city(), publicApi.zones(12), publicApi.hospitals(),
      ])
      setCity(c); setZones(z); setHospitals(h); setError(null)
    } catch (err) {
      setError(err?.message || 'Could not reach the public API.')
    }
  }
  useEffect(() => {
    refresh()
    tickRef.current = setInterval(refresh, TICK_MS)
    return () => clearInterval(tickRef.current)
  }, [])

  const minOf = (s) => s == null ? '—' : `${(s / 60).toFixed(1)}m`

  // Pre-compute zone heat scale.
  const maxActive = useMemo(
    () => Math.max(1, ...zones.map(z => z.active + z.last_24h * 0.1)),
    [zones],
  )

  return (
    <div className="min-h-screen bg-ink-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-line/60 bg-ink-900/70 backdrop-blur sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-3">
          <Heart className="w-5 h-5 text-sig-critical animate-pulse"/>
          <div className="flex-1">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
              {t('city.header_eyebrow')}
            </div>
            <div className="text-sm font-semibold">{t('city.header_subtitle')}</div>
          </div>
          <LangPicker compact/>
          <div className="text-[10px] font-mono text-slate-500 inline-flex items-center gap-1">
            <RefreshCw className="w-3 h-3"/>
            {city ? new Date(city.last_updated).toLocaleTimeString() : '—'}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {error && (
          <div className="card p-4 border-sig-critical/40 text-sm text-red-200">
            {error}
          </div>
        )}

        {/* Top KPIs */}
        <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat
            icon={Activity}
            label={t('city.kpi_active')}
            value={(city?.active_emergencies ?? 0) + (city?.pending_emergencies ?? 0)}
            hint={t('city.kpi_active_hint', {
              pending: city?.pending_emergencies ?? 0,
              active: city?.active_emergencies ?? 0,
            })}
            tint={(city?.pending_emergencies ?? 0) > 0 ? 'red' : 'cyan'}
          />
          <Stat
            icon={Truck}
            label={t('city.kpi_units')}
            value={city?.available_ambulances ?? '—'}
            hint={t('city.kpi_units_hint', { busy: city?.busy_ambulances ?? 0 })}
            tint={(city?.available_ambulances ?? 0) <= 2 ? 'amber' : 'emerald'}
          />
          <Stat
            icon={Clock}
            label={t('city.kpi_response')}
            value={minOf(city?.avg_response_time_last_hour_seconds)}
            hint={t('city.kpi_response_hint', { count: city?.calls_last_hour ?? 0 })}
            tint="cyan"
          />
          <Stat
            icon={ShieldOff}
            label={t('city.kpi_diversion')}
            value={`${city?.hospitals_on_diversion ?? 0}/${city?.hospitals_total ?? 0}`}
            hint={t('city.kpi_diversion_hint', {
              icu: city?.icu_beds_available ?? 0,
              general: city?.general_beds_available ?? 0,
            })}
            tint={(city?.hospitals_on_diversion ?? 0) > 0 ? 'amber' : 'slate'}
          />
        </section>

        {/* Zones heatmap */}
        <section className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <MapPin className="w-5 h-5 text-cyan-400"/>
            <h2 className="text-xl font-bold">{t('city.zones_title')}</h2>
            <span className="text-xs text-slate-500 font-mono ml-auto">
              {t('city.zones_subtitle', { count: zones.length })}
            </span>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {zones.map(z => {
              const intensity = (z.active + z.last_24h * 0.1) / maxActive
              const bg = `rgba(239,68,68,${0.08 + intensity * 0.55})`
              const border = z.active > 0 ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(48,55,72,0.6)'
              return (
                <div key={z.zone_id}
                     className="rounded-lg p-3 text-sm transition-all"
                     style={{ background: bg, border }}>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-300">
                    zone {String(z.zone_id).padStart(2, '0')}
                  </div>
                  <div className="text-2xl font-bold leading-none mt-1">{z.active}</div>
                  <div className="text-[11px] text-slate-300/80 mt-1">
                    active
                  </div>
                  <div className="text-[10px] font-mono text-slate-400/80 mt-2">
                    24h: {z.last_24h}
                    {z.avg_response_seconds != null && (
                      <> · avg {(z.avg_response_seconds / 60).toFixed(1)}m</>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="text-[10px] font-mono text-slate-500 mt-3">
            {t('city.zones_help')}
          </div>
        </section>

        {/* Hospital availability */}
        <section className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <HospitalIcon className="w-5 h-5 text-emerald-400"/>
            <h2 className="text-xl font-bold">{t('city.hospitals_title')}</h2>
            <span className="text-xs text-slate-500 font-mono ml-auto">
              {t('city.hospitals_subtitle', { count: hospitals.length })}
            </span>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            {hospitals.map(h => {
              const icuPct = h.total_beds_icu > 0 ? Math.round(h.available_beds_icu / h.total_beds_icu * 100) : 0
              const genPct = h.total_beds_general > 0 ? Math.round(h.available_beds_general / h.total_beds_general * 100) : 0
              return (
                <div key={h.id} className={`card p-3 border ${h.is_diversion ? 'border-amber-400/40' : 'border-line/40'}`}>
                  <div className="flex items-start gap-3">
                    <Bed className={`w-4 h-4 mt-1 shrink-0 ${h.is_diversion ? 'text-amber-300' : 'text-emerald-400'}`}/>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{h.name}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {h.specialties.slice(0, 4).join(' · ')}
                      </div>
                      {h.is_diversion && (
                        <div className="text-[10px] font-mono uppercase text-amber-300 mt-1">
                          {t('city.on_diversion')}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <BedBar label="general" pct={genPct}
                            available={h.available_beds_general} total={h.total_beds_general}/>
                    <BedBar label="ICU" pct={icuPct}
                            available={h.available_beds_icu} total={h.total_beds_icu}/>
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 mt-2">
                    {t('city.er_wait', { min: h.er_wait_minutes })}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        <footer className="text-center text-[10px] font-mono text-slate-600 pt-4">
          {t('city.footer', { seconds: TICK_MS / 1000 })}
        </footer>
      </main>
    </div>
  )
}


function Stat({ icon: Icon, label, value, hint, tint }) {
  const colours = {
    red: 'border-sig-critical/40 text-red-200 bg-sig-critical/5',
    amber: 'border-amber-400/40 text-amber-200 bg-amber-400/5',
    cyan: 'border-cyan-400/40 text-cyan-200 bg-cyan-400/5',
    emerald: 'border-emerald-400/40 text-emerald-200 bg-emerald-400/5',
    slate: 'border-line/40 text-slate-200 bg-ink-700/30',
  }[tint || 'slate']
  return (
    <div className={`card p-4 border ${colours}`}>
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider opacity-80">
        <Icon className="w-3.5 h-3.5"/>{label}
      </div>
      <div className="text-3xl font-bold mt-1.5">{value ?? '—'}</div>
      {hint && <div className="text-[11px] opacity-70 mt-1">{hint}</div>}
    </div>
  )
}

function BedBar({ label, pct, available, total }) {
  const colour = pct >= 30 ? 'bg-emerald-400' : pct >= 10 ? 'bg-amber-400' : 'bg-sig-critical'
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] font-mono">
        <span className="text-slate-400 uppercase">{label}</span>
        <span className="text-slate-300">{available}/{total}</span>
      </div>
      <div className="h-1.5 mt-1 rounded-full bg-ink-700 overflow-hidden">
        <div className={`h-full ${colour}`} style={{ width: `${Math.min(100, pct)}%` }}/>
      </div>
    </div>
  )
}
