import { useEffect, useMemo, useState } from 'react'
import {
  Users, ShieldCheck, ClipboardList, BarChart3, Loader2, Plus, Trash2,
  Pencil, X, Check, Filter, Zap, AlertTriangle, Film, Play, Square,
  RotateCw,
} from 'lucide-react'

import { adminApi } from '../api/client.js'
import { useAuthStore } from '../store/auth.js'
import { useUiStore } from '../store/ui.js'

const TABS = [
  { id: 'overview', label: 'Overview', icon: BarChart3 },
  { id: 'users',    label: 'Users',    icon: Users },
  { id: 'audit',    label: 'Audit',    icon: ClipboardList },
  { id: 'demo',     label: 'Demo',     icon: Film },
  { id: 'chaos',    label: 'Chaos lab', icon: Zap },
]

const ROLES = ['dispatcher', 'paramedic', 'hospital_staff', 'admin', 'patient']

export default function Admin() {
  const me = useAuthStore(s => s.user)
  const [tab, setTab] = useState('overview')

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-line/60 bg-ink-900/40 px-6 py-3 flex items-center gap-3">
        <ShieldCheck className="w-5 h-5 text-amber-400"/>
        <div className="flex-1">
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">admin</div>
          <div className="text-sm font-semibold">System administration</div>
        </div>
      </div>

      <div className="border-b border-line/40 px-6 flex gap-1">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 transition-all
                       ${tab === t.id
                         ? 'border-amber-400 text-amber-200'
                         : 'border-transparent text-slate-400 hover:text-slate-200'}`}>
            <t.icon className="w-3.5 h-3.5"/>{t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-6">
        {tab === 'overview' && <OverviewTab/>}
        {tab === 'users'    && <UsersTab me={me}/>}
        {tab === 'audit'    && <AuditTab/>}
        {tab === 'demo'     && <DemoTab/>}
        {tab === 'chaos'    && <ChaosTab/>}
      </div>
    </div>
  )
}


// ── Overview ───────────────────────────────────────────────────────────────
function OverviewTab() {
  const [data, setData] = useState(null)
  const toast = useUiStore(s => s.toast)

  useEffect(() => {
    (async () => {
      try { setData(await adminApi.overview()) }
      catch (e) { toast(e?.response?.data?.detail || 'Overview failed', 'critical') }
    })()
    const t = setInterval(async () => {
      try { setData(await adminApi.overview()) } catch {}
    }, 8000)
    return () => clearInterval(t)
  }, [])

  if (!data) return <Loader/>

  return (
    <div className="space-y-6">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Users"            value={data.total_users}/>
        <Stat label="Hospitals"        value={data.total_hospitals}
              hint={`${data.hospitals_on_diversion} on diversion`}/>
        <Stat label="Ambulances avail" value={data.available_ambulances}
              hint={`of ${data.total_ambulances} · ${data.busy_ambulances} busy`}/>
        <Stat label="Active dispatches" value={data.active_dispatches}
              hint={`${data.dispatches_today} today · ${data.pending_emergencies} pending`}/>
      </div>

      <div className="card p-5">
        <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400 mb-3">
          users by role
        </div>
        <div className="grid sm:grid-cols-5 gap-2">
          {ROLES.map(r => {
            const found = data.user_counts.find(u => u.role === r)
            const c = found?.count || 0
            return (
              <div key={r} className="card p-3 border-line/40">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">{r}</div>
                <div className="text-2xl font-bold mt-1">{c}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="card p-4">
      <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
      {hint && <div className="text-[11px] text-slate-500 mt-1">{hint}</div>}
    </div>
  )
}


// ── Users ──────────────────────────────────────────────────────────────────
function UsersTab({ me }) {
  const [users, setUsers] = useState([])
  const [filterRole, setFilterRole] = useState('')
  const [showOnlyActive, setShowOnlyActive] = useState(true)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(null)
  const toast = useUiStore(s => s.toast)

  async function load() {
    try {
      const params = {}
      if (filterRole) params.role = filterRole
      if (showOnlyActive) params.is_active = true
      setUsers(await adminApi.listUsers(params))
    } catch (e) {
      toast(e?.response?.data?.detail || 'Load failed', 'critical')
    }
  }
  useEffect(() => { load() }, [filterRole, showOnlyActive])

  async function deactivate(u) {
    if (u.id === me?.id) return toast('Cannot deactivate yourself.', 'critical')
    if (!confirm(`Deactivate ${u.username}? They won't be able to log in.`)) return
    try { await adminApi.deactivateUser(u.id); load() }
    catch (e) { toast(e?.response?.data?.detail || 'Deactivate failed', 'critical') }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-slate-500"/>
        <select className="field !py-1.5 text-xs"
                value={filterRole} onChange={e => setFilterRole(e.target.value)}>
          <option value="">all roles</option>
          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <label className="text-xs text-slate-400 flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={showOnlyActive}
                 onChange={e => setShowOnlyActive(e.target.checked)}/>
          active only
        </label>
        <div className="flex-1"/>
        <button onClick={() => setCreating(true)} className="btn-danger text-xs">
          <Plus className="w-3.5 h-3.5"/>new user
        </button>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ink-900/60 text-[10px] font-mono uppercase tracking-wider text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">id</th>
              <th className="text-left px-4 py-2">username</th>
              <th className="text-left px-4 py-2">name</th>
              <th className="text-left px-4 py-2">email</th>
              <th className="text-left px-4 py-2">role</th>
              <th className="text-left px-4 py-2">active</th>
              <th className="text-right px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-t border-line/30 hover:bg-ink-800/30">
                <td className="px-4 py-2 font-mono text-xs">{u.id}</td>
                <td className="px-4 py-2 font-mono">{u.username}</td>
                <td className="px-4 py-2">{u.full_name || '—'}</td>
                <td className="px-4 py-2 text-slate-400 text-xs">{u.email}</td>
                <td className="px-4 py-2">
                  <span className="px-1.5 py-0.5 rounded border border-line text-[10px] font-mono uppercase">
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {u.is_active
                    ? <Check className="w-4 h-4 text-emerald-400"/>
                    : <X className="w-4 h-4 text-red-400"/>}
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="inline-flex gap-1">
                    <button onClick={() => setEditing(u)} className="p-1 text-slate-400 hover:text-cyan-300">
                      <Pencil className="w-3.5 h-3.5"/>
                    </button>
                    {u.is_active && u.id !== me?.id && (
                      <button onClick={() => deactivate(u)} className="p-1 text-slate-400 hover:text-red-400">
                        <Trash2 className="w-3.5 h-3.5"/>
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-slate-500 text-sm">No users.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {creating && (
        <UserDialog title="New user" onClose={() => setCreating(false)}
                    onSave={async (data) => {
                      try { await adminApi.createUser(data); setCreating(false); load(); toast('User created', 'success') }
                      catch (e) { toast(e?.response?.data?.detail || 'Create failed', 'critical') }
                    }}/>
      )}
      {editing && (
        <UserDialog title={`Edit ${editing.username}`} initial={editing}
                    onClose={() => setEditing(null)}
                    onSave={async (data) => {
                      try { await adminApi.updateUser(editing.id, data); setEditing(null); load(); toast('User updated', 'success') }
                      catch (e) { toast(e?.response?.data?.detail || 'Update failed', 'critical') }
                    }}/>
      )}
    </div>
  )
}

function UserDialog({ title, initial, onClose, onSave }) {
  const [draft, setDraft] = useState(initial ? {
    username: initial.username, email: initial.email, full_name: initial.full_name,
    role: initial.role, is_active: initial.is_active, password: '',
  } : { username: '', email: '', full_name: '', role: 'dispatcher', is_active: true, password: '' })
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    const data = { ...draft }
    if (initial) {
      delete data.username
      if (!data.password) delete data.password
    }
    try { await onSave(data) } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm">
      <form onSubmit={submit} className="card p-6 w-[440px] max-w-[92vw] space-y-3">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-bold">{title}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-100">
            <X className="w-4 h-4"/>
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Username">
            <input className="field font-mono" required disabled={!!initial} minLength={3}
                   value={draft.username}
                   onChange={e => setDraft({...draft, username: e.target.value})}/>
          </Field>
          <Field label="Role">
            <select className="field" value={draft.role}
                    onChange={e => setDraft({...draft, role: e.target.value})}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <Field label="Email" wide>
            <input type="email" className="field" required
                   value={draft.email}
                   onChange={e => setDraft({...draft, email: e.target.value})}/>
          </Field>
          <Field label="Full name" wide>
            <input className="field"
                   value={draft.full_name || ''}
                   onChange={e => setDraft({...draft, full_name: e.target.value})}/>
          </Field>
          <Field label={initial ? "New password (optional)" : "Password"} wide>
            <input type="password" className="field" minLength={6}
                   required={!initial}
                   value={draft.password || ''}
                   onChange={e => setDraft({...draft, password: e.target.value})}/>
          </Field>
          {initial && (
            <label className="col-span-2 text-sm flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={draft.is_active}
                     onChange={e => setDraft({...draft, is_active: e.target.checked})}/>
              Active
            </label>
          )}
        </div>
        <div className="flex gap-2 pt-3 border-t border-line/30">
          <button type="submit" disabled={busy} className="btn-danger flex-1">
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-4">Cancel</button>
        </div>
      </form>
    </div>
  )
}


// ── Audit ──────────────────────────────────────────────────────────────────
function AuditTab() {
  const [rows, setRows] = useState([])
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const toast = useUiStore(s => s.toast)

  async function load() {
    try {
      const params = { limit: 200 }
      if (entityType) params.entity_type = entityType
      if (action) params.action = action
      setRows(await adminApi.auditLog(params))
    } catch (e) {
      toast(e?.response?.data?.detail || 'Audit load failed', 'critical')
    }
  }
  useEffect(() => { load() }, [entityType, action])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-slate-500"/>
        <input className="field !py-1.5 text-xs" placeholder="entity_type (e.g. emergency)"
               value={entityType} onChange={e => setEntityType(e.target.value)}/>
        <input className="field !py-1.5 text-xs" placeholder="action (e.g. dispatch_created)"
               value={action} onChange={e => setAction(e.target.value)}/>
        <span className="text-xs text-slate-500 ml-auto">{rows.length} entries</span>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-ink-900/60 text-[10px] font-mono uppercase tracking-wider text-slate-500">
            <tr>
              <th className="text-left px-3 py-2">when</th>
              <th className="text-left px-3 py-2">user</th>
              <th className="text-left px-3 py-2">action</th>
              <th className="text-left px-3 py-2">entity</th>
              <th className="text-left px-3 py-2">details</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className="border-t border-line/30 align-top">
                <td className="px-3 py-2 font-mono whitespace-nowrap">
                  {new Date(r.timestamp).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-mono">{r.user_id ?? '—'}</td>
                <td className="px-3 py-2 font-mono">{r.action}</td>
                <td className="px-3 py-2">
                  {r.entity_type}{r.entity_id ? ` #${r.entity_id}` : ''}
                </td>
                <td className="px-3 py-2 font-mono text-slate-400 break-all max-w-md">
                  {r.details ? JSON.stringify(r.details) : '—'}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                No audit entries match.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}


// ── Helpers ────────────────────────────────────────────────────────────────
function Field({ label, children, wide }) {
  return (
    <div className={wide ? 'col-span-2' : ''}>
      <label className="field-label">{label}</label>
      {children}
    </div>
  )
}

function Loader() {
  return (
    <div className="flex items-center gap-2 text-slate-500 text-sm">
      <Loader2 className="w-4 h-4 animate-spin"/> loading…
    </div>
  )
}


// ── Chaos lab ──────────────────────────────────────────────────────────────
const SCENARIO_HINTS = {
  routing_provider_down: {
    title: 'Routing provider outage',
    description: 'Force a named routing provider (osrm/ors/mapbox/here, or *) ' +
      'to fail every call. Verifies the chain falls through to the next ' +
      'provider — and ultimately the haversine fallback.',
  },
  severity_predictor_slow: {
    title: 'Slow severity predictor',
    description: 'Inject a synthetic delay before the severity classifier ' +
      'returns. Demonstrates that callers tolerate slow AI without blocking ' +
      'the dispatch path.',
  },
  dispatch_failure_rate: {
    title: 'Dispatch failure injection',
    description: 'Deterministic per-emergency coin flip; failed attempts ' +
      'raise DispatchError with chaos: prefix. Stress-tests retry / ' +
      're-route logic.',
  },
}

function ChaosTab() {
  const toast = useUiStore(s => s.toast)
  const [state, setState] = useState(null)
  const [params, setParams] = useState({
    routing_provider_down: { provider: '*' },
    severity_predictor_slow: { delay_ms: 800 },
    dispatch_failure_rate: { rate: 0.5 },
  })

  async function load() {
    try { setState(await adminApi.chaosState()) }
    catch (e) { toast(e?.response?.data?.detail || 'Load failed', 'critical') }
  }
  useEffect(() => { load() }, [])

  async function inject(scenario) {
    try {
      await adminApi.chaosInject({ scenario, ...params[scenario] })
      toast(`Injected ${scenario}`, 'success')
      load()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Inject failed', 'critical')
    }
  }

  async function clear(scenario) {
    try {
      const r = await adminApi.chaosClear(scenario)
      toast(scenario ? `Cleared ${scenario}` : `Cleared ${r.cleared} scenario(s)`,
            'success')
      load()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Clear failed', 'critical')
    }
  }

  const activeByName = useMemo(() => {
    const m = {}
    for (const a of state?.active || []) m[a.scenario] = a
    return m
  }, [state])

  if (!state) return <Loader/>

  return (
    <div className="space-y-5">
      <div className="card p-4 border-amber-500/30 bg-amber-500/5 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0"/>
        <div className="text-xs text-amber-100/90 leading-relaxed">
          <div className="font-semibold mb-1">Chaos lab — admin only.</div>
          Injected faults stay active until cleared or until the backend
          restarts. Nothing here mutates the database; effects are confined to
          live request paths. Use during demos to show graceful degradation,
          and clear before real traffic.
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">
          {state.active.length} active · {state.available_scenarios.length} available
        </div>
        {state.active.length > 0 && (
          <button onClick={() => clear()} className="btn-ghost text-xs">
            Clear all
          </button>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {state.available_scenarios.map(s => {
          const hint = SCENARIO_HINTS[s] || { title: s, description: '' }
          const active = activeByName[s]
          const p = params[s] || {}
          return (
            <div key={s} className={`card p-4 ${active ? 'border-amber-400/60 bg-amber-500/5' : ''}`}>
              <div className="flex items-center gap-2 mb-2">
                <Zap className={`w-3.5 h-3.5 ${active ? 'text-amber-400' : 'text-slate-500'}`}/>
                <div className="text-sm font-semibold">{hint.title}</div>
              </div>
              <div className="text-[11px] text-slate-400 leading-relaxed mb-3">
                {hint.description}
              </div>

              {s === 'routing_provider_down' && (
                <div className="mb-3">
                  <label className="field-label">Provider</label>
                  <select className="field !py-1.5 text-xs" value={p.provider}
                          onChange={e => setParams(x => ({ ...x, [s]: { provider: e.target.value } }))}>
                    <option value="*">All providers</option>
                    <option value="osrm">osrm</option>
                    <option value="ors">ors</option>
                    <option value="mapbox">mapbox</option>
                    <option value="here">here</option>
                  </select>
                </div>
              )}
              {s === 'severity_predictor_slow' && (
                <div className="mb-3">
                  <label className="field-label">Delay (ms)</label>
                  <input className="field !py-1.5 text-xs" type="number" min={0} max={10000}
                         value={p.delay_ms}
                         onChange={e => setParams(x => ({ ...x, [s]: { delay_ms: Number(e.target.value) } }))}/>
                </div>
              )}
              {s === 'dispatch_failure_rate' && (
                <div className="mb-3">
                  <label className="field-label">Failure rate</label>
                  <input type="range" min={0} max={1} step={0.05}
                         value={p.rate}
                         onChange={e => setParams(x => ({ ...x, [s]: { rate: Number(e.target.value) } }))}
                         className="w-full"/>
                  <div className="text-[10px] font-mono text-slate-400 mt-1">
                    {(p.rate * 100).toFixed(0)}% of dispatch attempts fail
                  </div>
                </div>
              )}

              {active && (
                <div className="mt-2 mb-3 p-2 rounded bg-ink-900/60 border border-amber-400/30">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-amber-300 mb-1">
                    Active
                  </div>
                  <div className="text-[11px] font-mono text-slate-300">
                    {Object.entries(active)
                      .filter(([k]) => !['scenario', 'injected_at', 'seed'].includes(k))
                      .filter(([, v]) => v !== null && v !== undefined)
                      .map(([k, v]) => `${k}=${v}`).join(' · ')}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                {!active ? (
                  <button onClick={() => inject(s)} className="btn-primary text-xs flex-1">
                    Inject
                  </button>
                ) : (
                  <>
                    <button onClick={() => inject(s)} className="btn-ghost text-xs flex-1">
                      Re-inject
                    </button>
                    <button onClick={() => clear(s)} className="btn-ghost text-xs flex-1
                                                              !border-amber-400/40 !text-amber-200">
                      Clear
                    </button>
                  </>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}


// ── Demo runner + replay ─────────────────────────────────────────────────
function DemoTab() {
  const toast = useUiStore(s => s.toast)
  const [scenarios, setScenarios] = useState([])
  const [captures, setCaptures] = useState([])
  const [demoState, setDemoState] = useState(null)
  const [replayState, setReplayState] = useState(null)
  const [picked, setPicked] = useState('cardiac_chain')
  const [speed, setSpeed] = useState(1.0)
  const [replaySpeed, setReplaySpeed] = useState(1.0)
  const [replayPick, setReplayPick] = useState('')

  async function load() {
    try {
      const [scn, caps, ds, rs] = await Promise.all([
        adminApi.demoScenarios(),
        adminApi.replayList(),
        adminApi.demoStatus(),
        adminApi.replayStatus(),
      ])
      setScenarios(scn)
      setCaptures(caps)
      setDemoState(ds)
      setReplayState(rs)
      if (!replayPick && caps.length) setReplayPick(caps[0].session_id)
    } catch (e) {
      toast(e?.response?.data?.detail || 'Load failed', 'critical')
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(async () => {
      try {
        const [ds, rs] = await Promise.all([
          adminApi.demoStatus(),
          adminApi.replayStatus(),
        ])
        setDemoState(ds)
        setReplayState(rs)
      } catch {}
    }, 1500)
    return () => clearInterval(t)
  }, [])

  async function startDemo() {
    try {
      await adminApi.demoStart({ scenario: picked, speed })
      toast(`Started ${picked}`, 'success')
      load()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Start failed', 'critical')
    }
  }

  async function stopDemo() {
    try {
      await adminApi.demoStop()
      toast('Stopped', 'success')
      load()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Stop failed', 'critical')
    }
  }

  async function startReplay() {
    if (!replayPick) return
    try {
      await adminApi.replayStart({ session_id: replayPick, speed: replaySpeed })
      toast(`Replaying ${replayPick}`, 'success')
      load()
    } catch (e) {
      toast(e?.response?.data?.detail || 'Replay failed', 'critical')
    }
  }

  const isRunning = demoState?.running
  const isReplayRunning = replayState?.running
  const ds = demoState?.state
  const progressPct = ds && ds.total_beats > 0
    ? Math.min(100, Math.round((ds.current_beat / ds.total_beats) * 100))
    : 0
  const rs = replayState?.state
  const replayProgressPct = rs && rs.frames_total > 0
    ? Math.min(100, Math.round((rs.frames_emitted / rs.frames_total) * 100))
    : 0

  return (
    <div className="space-y-5">
      <div className="card p-4 border-cyan-400/30 bg-cyan-500/5 flex items-start gap-3">
        <Film className="w-5 h-5 text-cyan-300 mt-0.5 shrink-0"/>
        <div className="text-xs text-cyan-100/90 leading-relaxed">
          <div className="font-semibold mb-1">Cinematic demo + replay.</div>
          Scripted scenarios drive the live UI through the real pipeline —
          Emergency rows are inserted, dispatch_engine runs, MCI service
          classifies victims. Every run captures its Socket.IO frames to a
          JSONL file under <span className="font-mono">backend/replays/</span>;
          replays re-emit those frames at any speed without touching the DB.
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Demo runner card */}
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Play className="w-3.5 h-3.5 text-emerald-400"/>
            <div className="text-sm font-semibold">Demo runner</div>
          </div>

          <div className="mb-3">
            <label className="field-label">Scenario</label>
            <select className="field !py-1.5 text-xs" value={picked}
                    disabled={isRunning}
                    onChange={e => setPicked(e.target.value)}>
              {scenarios.map(s => (
                <option key={s.name} value={s.name}>
                  {s.name} ({s.beats} beats)
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="field-label">Speed × {speed.toFixed(1)}</label>
            <input type="range" min={0.5} max={10} step={0.5}
                   value={speed} disabled={isRunning}
                   onChange={e => setSpeed(Number(e.target.value))}
                   className="w-full"/>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              0.5× = half speed · 10× = compressed for quick smoke
            </div>
          </div>

          {ds && (
            <div className="mb-3 p-2 rounded bg-ink-900/60 border border-line/40">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-slate-300">{ds.scenario}</span>
                <span className={ds.error ? 'text-rose-400' : 'text-slate-400'}>
                  beat {ds.current_beat}/{ds.total_beats}
                </span>
              </div>
              <div className="h-1.5 bg-ink-950 rounded-full overflow-hidden mt-1.5">
                <div className="h-full bg-emerald-400 transition-all"
                     style={{ width: `${progressPct}%` }}/>
              </div>
              {ds.last_narration && (
                <div className="text-[11px] text-slate-300 mt-2 italic">
                  "{ds.last_narration}"
                </div>
              )}
              {ds.error && (
                <div className="text-[11px] text-rose-300 mt-1 font-mono">
                  {ds.error}
                </div>
              )}
              <div className="text-[10px] font-mono text-slate-500 mt-1">
                {ds.events_captured} events captured
                {ds.finished ? ' · finished' : ''}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            {!isRunning ? (
              <button onClick={startDemo} className="btn-primary text-xs flex-1">
                <Play className="w-3 h-3 inline mr-1"/> Start scenario
              </button>
            ) : (
              <button onClick={stopDemo} className="btn-ghost text-xs flex-1
                                                   !border-rose-400/40 !text-rose-200">
                <Square className="w-3 h-3 inline mr-1"/> Stop
              </button>
            )}
          </div>
        </div>

        {/* Replay card */}
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <RotateCw className="w-3.5 h-3.5 text-cyan-300"/>
            <div className="text-sm font-semibold">Replay capture</div>
          </div>

          <div className="mb-3">
            <label className="field-label">
              Captured session{' '}
              <span className="text-slate-500">({captures.length})</span>
            </label>
            <select className="field !py-1.5 text-xs" value={replayPick}
                    disabled={isReplayRunning}
                    onChange={e => setReplayPick(e.target.value)}>
              {captures.length === 0 && <option value="">No captures yet</option>}
              {captures.map(c => (
                <option key={c.session_id} value={c.session_id}>
                  {c.session_id} · {c.frames} frames
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="field-label">Speed × {replaySpeed.toFixed(1)}</label>
            <input type="range" min={0.5} max={20} step={0.5}
                   value={replaySpeed} disabled={isReplayRunning}
                   onChange={e => setReplaySpeed(Number(e.target.value))}
                   className="w-full"/>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              Replay re-emits the captured Socket.IO frames; no DB writes.
            </div>
          </div>

          {rs && (
            <div className="mb-3 p-2 rounded bg-ink-900/60 border border-line/40">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-slate-300 truncate">{rs.session_id}</span>
                <span className="text-slate-400">
                  {rs.frames_emitted}/{rs.frames_total}
                </span>
              </div>
              <div className="h-1.5 bg-ink-950 rounded-full overflow-hidden mt-1.5">
                <div className="h-full bg-cyan-400 transition-all"
                     style={{ width: `${replayProgressPct}%` }}/>
              </div>
              <div className="text-[10px] font-mono text-slate-500 mt-1">
                speed × {rs.speed?.toFixed(1)}{rs.finished ? ' · finished' : ''}
              </div>
            </div>
          )}

          <button onClick={startReplay}
                  disabled={!replayPick || isReplayRunning}
                  className="btn-primary text-xs w-full disabled:opacity-50">
            <RotateCw className="w-3 h-3 inline mr-1"/>
            {isReplayRunning ? 'Replaying…' : 'Start replay'}
          </button>
        </div>
      </div>
    </div>
  )
}
