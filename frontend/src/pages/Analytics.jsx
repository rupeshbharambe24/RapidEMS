import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

import KPICard from '../components/KPICard.jsx'
import { analyticsApi } from '../api/client.js'
import { Activity, TrendingUp, AlertTriangle, Truck, Building2, Bed } from 'lucide-react'

export default function Analytics() {
  const [kpis, setKpis] = useState(null)
  const [hotspots, setHotspots] = useState(null)

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 10000)
    return () => clearInterval(t)
  }, [])

  async function refresh() {
    try {
      const [k, h] = await Promise.all([analyticsApi.kpis(), analyticsApi.hotspots(12)])
      setKpis(k); setHotspots(h)
    } catch {}
  }

  // sort zones by next-24h-total descending
  const zonesSorted = [...(hotspots?.zones || [])].sort((a, b) => b.next_24h_total - a.next_24h_total)
  const maxTotal = zonesSorted[0]?.next_24h_total || 1

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="h-eyebrow mb-1">Forecast & KPIs</div>
        <h1 className="text-2xl font-bold">Demand Analytics</h1>
        <p className="text-sm text-slate-400 mt-0.5">LSTM hotspot forecast + operational metrics</p>
      </div>

      {/* KPIs row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <KPICard label="24h Calls"      value={kpis?.total_emergencies_24h ?? '—'}    accent="cyan"    icon={Activity}/>
        <KPICard label="Pending"        value={kpis?.pending_emergencies ?? '—'}      accent="red"     icon={AlertTriangle}/>
        <KPICard label="Active"         value={kpis?.active_dispatches ?? '—'}        accent="amber"   icon={TrendingUp}/>
        <KPICard label="Available"      value={kpis?.available_ambulances ?? '—'}     accent="emerald" icon={Truck}/>
        <KPICard label="Diversions"     value={kpis?.hospitals_on_diversion ?? '—'}   accent={kpis?.hospitals_on_diversion ? 'amber' : 'slate'} icon={Building2}/>
        <KPICard label="Avg Severity"   value={kpis?.avg_severity?.toFixed(2) ?? '—'} accent="slate"   icon={Bed}/>
      </div>

      {/* Hotspot heatmap (next-hour demand) */}
      <div className="card p-5 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="h-eyebrow mb-1">Demand heatmap</div>
            <h2 className="text-lg font-semibold">Next-hour predicted incidents per zone</h2>
            <p className="text-xs text-slate-500 mt-0.5">Source: LSTM forecaster (Notebook 5) — heuristic fallback if model missing</p>
          </div>
        </div>

        {/* Grid cells */}
        <div className="grid grid-cols-4 gap-2">
          {zonesSorted.slice().sort((a, b) => a.zone_id - b.zone_id).map(z => {
            const intensity = Math.min(1, z.next_24h_total / maxTotal)
            const bg = `rgba(239, 68, 68, ${0.10 + intensity * 0.65})`
            const ring = intensity > 0.7 ? 'border-sig-critical/60' : intensity > 0.4 ? 'border-sig-moderate/50' : 'border-line'
            return (
              <div key={z.zone_id}
                className={`relative p-3 rounded border ${ring} transition-all hover:scale-[1.02]`}
                style={{ background: bg }}>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-300">Zone {z.zone_id.toString().padStart(2,'0')}</div>
                <div className="font-mono text-2xl tabular-nums mt-1">{z.next_hour_demand.toFixed(1)}</div>
                <div className="text-[10px] font-mono text-slate-300 mt-0.5">24h: {z.next_24h_total.toFixed(0)}</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Bar chart of next-24h-total per zone */}
      <div className="card p-5">
        <div className="mb-4">
          <div className="h-eyebrow mb-1">Forecast distribution</div>
          <h2 className="text-lg font-semibold">Predicted 24-hour incidents per zone</h2>
        </div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={zonesSorted} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3450"/>
              <XAxis dataKey="zone_id" stroke="#94a3b8" fontSize={11} tickFormatter={v => `Z${v}`}/>
              <YAxis stroke="#94a3b8" fontSize={11}/>
              <Tooltip
                contentStyle={{ background: '#10162a', border: '1px solid #2a3450', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}
                formatter={(v, name) => [v.toFixed(2), name === 'next_24h_total' ? '24h total' : name]}
              />
              <Bar dataKey="next_24h_total" radius={[4, 4, 0, 0]}>
                {zonesSorted.map((z) => {
                  const intensity = Math.min(1, z.next_24h_total / maxTotal)
                  const c = intensity > 0.7 ? '#ef4444' : intensity > 0.4 ? '#f59e0b' : '#06b6d4'
                  return <Cell key={z.zone_id} fill={c}/>
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
