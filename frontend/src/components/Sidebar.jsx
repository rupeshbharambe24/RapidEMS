import { NavLink } from 'react-router-dom'
import { LayoutDashboard, PhoneCall, Truck, Building2, BarChart3, LogOut, ShieldCheck } from 'lucide-react'

import { useAuthStore } from '../store/auth.js'

const NAV = [
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Console',     code: '01' },
  { to: '/intake',     icon: PhoneCall,       label: 'Intake',      code: '02' },
  { to: '/ambulances', icon: Truck,           label: 'Fleet',       code: '03' },
  { to: '/hospitals',  icon: Building2,       label: 'Facilities',  code: '04' },
  { to: '/analytics',  icon: BarChart3,       label: 'Analytics',   code: '05' },
]

const ADMIN_NAV = [
  { to: '/admin', icon: ShieldCheck, label: 'Admin', code: '00' },
]

export default function Sidebar() {
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)

  return (
    <aside className="w-60 shrink-0 bg-ink-900/70 backdrop-blur border-r border-line/60 flex flex-col">
      {/* Brand */}
      <div className="px-5 pt-5 pb-4 border-b border-line/50">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded bg-gradient-to-br from-sig-critical to-sig-serious flex items-center justify-center shadow-[0_0_18px_-4px_rgba(239,68,68,.55)]">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.7" strokeLinecap="round">
              <path d="M9 4h6v5h5v6h-5v5H9v-5H4V9h5z"/>
            </svg>
          </div>
          <div>
            <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-slate-400 leading-none">Code 01</div>
            <div className="text-sm font-semibold leading-tight">Response Console</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, icon: Icon, label, code }) => (
          <NavLink
            key={to} to={to}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-3 py-2 rounded text-sm transition-all
               ${isActive
                  ? 'bg-cyan-400/10 text-cyan-300 border-l-2 border-cyan-400 shadow-[inset_0_0_24px_-12px_rgba(6,182,212,.5)]'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-ink-800/60 border-l-2 border-transparent'}`
            }
          >
            <Icon className="w-4 h-4 shrink-0" strokeWidth={2.2} />
            <span className="font-medium">{label}</span>
            <span className="ml-auto font-mono text-[10px] text-slate-500 group-hover:text-slate-400">{code}</span>
          </NavLink>
        ))}

        {user?.role === 'admin' && (
          <div className="pt-3 mt-3 border-t border-line/40 space-y-1">
            {ADMIN_NAV.map(({ to, icon: Icon, label, code }) => (
              <NavLink
                key={to} to={to}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 py-2 rounded text-sm transition-all
                   ${isActive
                      ? 'bg-amber-400/10 text-amber-200 border-l-2 border-amber-400 shadow-[inset_0_0_24px_-12px_rgba(251,191,36,.5)]'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-ink-800/60 border-l-2 border-transparent'}`
                }
              >
                <Icon className="w-4 h-4 shrink-0" strokeWidth={2.2} />
                <span className="font-medium">{label}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-500 group-hover:text-slate-400">{code}</span>
              </NavLink>
            ))}
          </div>
        )}
      </nav>

      {/* User block */}
      <div className="border-t border-line/50 p-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-ink-700 flex items-center justify-center text-xs font-mono uppercase">
            {user?.username?.slice(0, 2) || 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate">{user?.full_name || user?.username || 'User'}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">{user?.role || 'guest'}</div>
          </div>
          <button onClick={logout} title="Sign out"
            className="p-1.5 rounded text-slate-400 hover:text-sig-critical hover:bg-ink-800">
            <LogOut className="w-4 h-4" strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </aside>
  )
}
