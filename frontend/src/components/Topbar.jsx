import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Wifi, WifiOff, Activity } from 'lucide-react'

import { useUiStore } from '../store/ui.js'

const PAGE_TITLES = {
  '/dashboard':  ['Operations Console', 'Live tactical overview'],
  '/intake':     ['Emergency Intake',   'Patient triage + dispatch'],
  '/ambulances': ['Fleet Tracking',     'Ambulance positions + status'],
  '/hospitals':  ['Facility Status',    'Bed availability + diversion'],
  '/analytics':  ['Demand Forecast',    'LSTM hotspots + KPIs'],
}

export default function Topbar() {
  const loc = useLocation()
  const [now, setNow] = useState(new Date())
  const socketStatus = useUiStore(s => s.socketStatus)

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const [title, sub] = PAGE_TITLES[loc.pathname] || ['', '']

  const StatusIcon = socketStatus === 'online' ? Wifi : WifiOff
  const statusColor = socketStatus === 'online' ? 'text-sig-minimal' : 'text-sig-critical'
  const statusText  = socketStatus === 'online' ? 'LIVE' : socketStatus.toUpperCase()

  return (
    <header className="border-b border-line/60 bg-ink-900/40 backdrop-blur px-6 py-3 flex items-center gap-6">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-slate-500">{sub}</div>
        <div className="text-lg font-semibold text-slate-100 leading-tight">{title}</div>
      </div>

      {/* Live status */}
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className={`relative flex w-2 h-2`}>
          {socketStatus === 'online' && (
            <span className="animate-ping absolute inset-0 rounded-full bg-sig-minimal opacity-75" />
          )}
          <span className={`relative w-2 h-2 rounded-full ${socketStatus === 'online' ? 'bg-sig-minimal' : 'bg-sig-critical'}`} />
        </span>
        <span className={statusColor}>{statusText}</span>
      </div>

      {/* Connection */}
      <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400">
        <StatusIcon className="w-3.5 h-3.5" strokeWidth={2.2} />
        <span>SOCKET</span>
      </div>

      {/* Clock */}
      <div className="font-mono text-sm tabular-nums text-slate-200 border-l border-line pl-6">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 leading-none mb-0.5">UTC</div>
        <div>{now.toISOString().substring(11, 19)}</div>
      </div>
    </header>
  )
}
