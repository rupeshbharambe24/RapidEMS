import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock, AlertCircle } from 'lucide-react'

import { authApi } from '../api/client.js'
import { useAuthStore } from '../store/auth.js'

export default function Login() {
  const nav = useNavigate()
  const login = useAuthStore(s => s.login)
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr(null); setBusy(true)
    try {
      const r = await authApi.login(username, password)
      login(r.access_token, r.user)
      const role = r.user?.role
      nav(role === 'patient' ? '/patient'
          : role === 'paramedic' ? '/driver'
          : role === 'hospital_staff' ? '/hospital'
          : '/dashboard')
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Authentication failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-5 bg-ink-950 text-slate-100">
      {/* Left — branded panel */}
      <div className="lg:col-span-3 relative hidden lg:flex flex-col justify-between p-12
                      bg-gradient-to-br from-ink-900 via-ink-900 to-ink-800 overflow-hidden">
        {/* atmosphere */}
        <div className="absolute inset-0 opacity-30 pointer-events-none"
          style={{ background: 'radial-gradient(circle at 30% 30%, rgba(239,68,68,.18), transparent 50%), radial-gradient(circle at 70% 70%, rgba(6,182,212,.15), transparent 50%)' }}/>
        <div className="absolute inset-0 pointer-events-none scanlines opacity-40"/>

        <div className="relative">
          <div className="flex items-center gap-3 mb-12">
            <div className="w-12 h-12 rounded bg-gradient-to-br from-sig-critical to-sig-serious flex items-center justify-center shadow-glow-red">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.7" strokeLinecap="round">
                <path d="M9 4h6v5h5v6h-5v5H9v-5H4V9h5z"/>
              </svg>
            </div>
            <div>
              <div className="text-[11px] font-mono uppercase tracking-[0.22em] text-slate-400">CODE 01 ▸ SECURE TERMINAL</div>
              <div className="text-xl font-bold leading-tight">Emergency Response Console</div>
            </div>
          </div>
        </div>

        <div className="relative space-y-8">
          <div>
            <div className="h-eyebrow mb-3">Mission</div>
            <p className="text-2xl font-semibold leading-snug max-w-xl">
              Triage. Dispatch. Route to the closest capable hospital — <span className="text-cyan-300">in seconds</span>.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4 max-w-xl">
            {[
              ['5', 'ML models'],
              ['<60s', 'AI dispatch'],
              ['24', 'Hour forecast'],
            ].map(([n, l]) => (
              <div key={l} className="border-l-2 border-cyan-400/60 pl-3">
                <div className="font-mono text-2xl tabular-nums">{n}</div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-mono">{l}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">
          v1.0.0 ▸ build {new Date().getFullYear()} ▸ all systems nominal
        </div>
      </div>

      {/* Right — login form */}
      <div className="lg:col-span-2 flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-2 flex items-center gap-2">
            <Lock className="w-3 h-3"/> Sign in
          </div>
          <h1 className="text-3xl font-bold mb-1">Authenticate</h1>
          <p className="text-sm text-slate-400 mb-8">
            Defaults: <code className="font-mono text-cyan-300">admin</code> / <code className="font-mono text-cyan-300">admin123</code>
          </p>

          <div className="space-y-4">
            <div>
              <label className="field-label">Username</label>
              <input className="field font-mono" value={username}
                     onChange={e => setUsername(e.target.value)} autoFocus/>
            </div>
            <div>
              <label className="field-label">Password</label>
              <input type="password" className="field font-mono" value={password}
                     onChange={e => setPassword(e.target.value)}/>
            </div>

            {err && (
              <div className="flex items-center gap-2 text-sm text-sig-critical bg-sig-critical/10 border border-sig-critical/30 rounded px-3 py-2">
                <AlertCircle className="w-4 h-4"/>{err}
              </div>
            )}

            <button type="submit" disabled={busy}
              className="btn-primary w-full mt-2 disabled:opacity-50 disabled:cursor-not-allowed">
              {busy ? 'Authenticating…' : 'Authenticate ▸'}
            </button>
          </div>

          <div className="mt-8 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 text-center">
            Audited session ▸ all actions logged
          </div>
        </form>
      </div>
    </div>
  )
}
