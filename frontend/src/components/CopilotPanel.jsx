import { useEffect, useRef, useState } from 'react'
import { Sparkles, Loader2, Send, X, Wrench, Keyboard } from 'lucide-react'

import { copilotApi } from '../api/client.js'

const SAMPLE_PROMPTS = [
  'How many ambulances are available right now?',
  'Show me ALS units within 6 km of the city centre.',
  'Cardiac hospitals with at least 3 ICU beds and not on diversion?',
  'Pending SEV-1 and SEV-2 calls from the last 30 minutes?',
]

export default function CopilotPanel({ open, onClose }) {
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  // history: [{ q, answer, tools, latency_ms, provider, error }]
  const [history, setHistory] = useState([])
  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  // Focus the input when the panel opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 60)
  }, [open])

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history.length, busy])

  // ESC closes
  useEffect(() => {
    if (!open) return
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  async function ask(text) {
    const q = (text ?? query).trim()
    if (!q || busy) return
    setQuery('')
    setHistory(h => [...h, { q, pending: true }])
    setBusy(true)
    try {
      const r = await copilotApi.ask(q)
      setHistory(h => {
        const cp = [...h]
        const last = cp[cp.length - 1]
        if (last && last.pending) cp[cp.length - 1] = { ...last, ...r, pending: false }
        return cp
      })
    } catch (err) {
      setHistory(h => {
        const cp = [...h]
        const last = cp[cp.length - 1]
        if (last && last.pending) {
          cp[cp.length - 1] = {
            ...last, pending: false,
            answer: err?.response?.data?.detail || 'Copilot failed',
            error: 'request_failed',
          }
        }
        return cp
      })
    } finally { setBusy(false) }
  }

  return (
    <div
      className={`fixed inset-y-0 right-0 z-40 w-full sm:w-[440px] bg-ink-900/95 backdrop-blur
                  border-l border-line/60 flex flex-col shadow-2xl
                  transition-transform duration-200
                  ${open ? 'translate-x-0' : 'translate-x-full pointer-events-none'}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-line/50">
        <Sparkles className="w-4 h-4 text-amber-300"/>
        <div className="flex-1">
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">copilot</div>
          <div className="text-sm font-semibold">Ask the system anything</div>
        </div>
        <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-line/40 text-[10px] font-mono text-slate-400">
          <Keyboard className="w-3 h-3"/> esc
        </kbd>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-100 ml-1">
          <X className="w-4 h-4"/>
        </button>
      </div>

      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {history.length === 0 && (
          <div className="space-y-3">
            <div className="text-xs text-slate-400 leading-relaxed">
              I can read fleet, hospitals, emergencies, and KPIs. Try one:
            </div>
            <div className="space-y-1.5">
              {SAMPLE_PROMPTS.map(p => (
                <button key={p} onClick={() => ask(p)}
                  className="block w-full text-left text-xs px-3 py-2 rounded border border-line/40
                             hover:border-amber-400/40 hover:bg-amber-400/5 transition-all
                             text-slate-300">
                  {p}
                </button>
              ))}
            </div>
            <div className="text-[10px] font-mono text-slate-500 pt-2 border-t border-line/30">
              Read-only. The copilot can't dispatch — use the dashboard for that.
            </div>
          </div>
        )}
        {history.map((h, i) => (
          <Turn key={i} entry={h}/>
        ))}
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); ask() }}
        className="border-t border-line/50 p-3 flex items-end gap-2 bg-ink-900/80"
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault(); ask()
            }
          }}
          placeholder="Ask anything…  (Enter to send · Shift+Enter for newline)"
          className="field flex-1 resize-none min-h-[42px] max-h-[160px]"
        />
        <button type="submit" disabled={busy || !query.trim()}
                className="btn-danger px-3 py-2 disabled:opacity-40">
          {busy
            ? <Loader2 className="w-4 h-4 animate-spin"/>
            : <Send className="w-4 h-4"/>}
        </button>
      </form>
    </div>
  )
}


function Turn({ entry }) {
  return (
    <div className="space-y-2">
      <div className="text-sm bg-ink-700/40 border border-line/40 rounded p-2.5">
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5">you</div>
        {entry.q}
      </div>
      <div className={`text-sm rounded p-2.5 border ${
        entry.error
          ? 'bg-sig-critical/5 border-sig-critical/30'
          : 'bg-amber-400/5 border-amber-400/30'
      }`}>
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-amber-300">
            copilot
          </div>
          {entry.latency_ms != null && !entry.pending && (
            <div className="text-[9px] font-mono text-slate-500">
              {entry.provider} · {entry.latency_ms}ms
            </div>
          )}
        </div>
        {entry.pending ? (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin"/>thinking…
          </div>
        ) : (
          <>
            <div className="leading-relaxed whitespace-pre-wrap">{entry.answer}</div>
            {entry.tool_calls?.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[10px] font-mono text-slate-500 hover:text-slate-300 inline-flex items-center gap-1">
                  <Wrench className="w-3 h-3"/>
                  {entry.tool_calls.length} tool call{entry.tool_calls.length === 1 ? '' : 's'}
                </summary>
                <div className="mt-2 space-y-1.5">
                  {entry.tool_calls.map((t, i) => (
                    <div key={i} className="text-[10px] font-mono">
                      <div className="text-cyan-300">
                        {t.name}({Object.entries(t.arguments || {})
                          .map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
                      </div>
                      <div className="text-slate-500 truncate">{t.result_preview}</div>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  )
}
