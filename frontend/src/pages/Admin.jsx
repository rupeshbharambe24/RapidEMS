import { useEffect, useMemo, useState } from 'react'
import {
  Users, ShieldCheck, ClipboardList, BarChart3, Loader2, Plus, Trash2,
  Pencil, X, Check, Filter,
} from 'lucide-react'

import { adminApi } from '../api/client.js'
import { useAuthStore } from '../store/auth.js'
import { useUiStore } from '../store/ui.js'

const TABS = [
  { id: 'overview', label: 'Overview', icon: BarChart3 },
  { id: 'users',    label: 'Users',    icon: Users },
  { id: 'audit',    label: 'Audit',    icon: ClipboardList },
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
