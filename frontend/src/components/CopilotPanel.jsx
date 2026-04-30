import { useEffect, useRef, useState } from 'react'
import { Sparkles, Loader2, Send, X, Wrench, Keyboard, Mic, Square } from 'lucide-react'

import { copilotApi } from '../api/client.js'

// Browser MediaRecorder picks a sane container automatically; webm/opus is
// the most widely supported. If the browser doesn't expose MediaRecorder
// at all (Safari versions, hardened deployments), the mic button hides.
const VOICE_SUPPORTED =
  typeof window !== 'undefined' &&
  typeof navigator !== 'undefined' &&
  navigator.mediaDevices?.getUserMedia &&
  typeof window.MediaRecorder !== 'undefined'

const SAMPLE_PROMPTS = [
  'How many ambulances are available right now?',
  'Show me ALS units within 6 km of the city centre.',
  'Cardiac hospitals with at least 3 ICU beds and not on diversion?',
  'Pending SEV-1 and SEV-2 calls from the last 30 minutes?',
]

export default function CopilotPanel({ open, onClose }) {
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [voiceErr, setVoiceErr] = useState(null)
  // history: [{ q, answer, tools, latency_ms, provider, error }]
  const [history, setHistory] = useState([])
  const inputRef = useRef(null)
  const scrollRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])

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

  // ── Voice path ─────────────────────────────────────────────────────────
  // Press-and-hold on the mic: start recording. Release: stop and ship the
  // blob to /copilot/voice. The endpoint transcribes + answers in one round
  // trip; the transcript shows up as a regular history turn so the
  // dispatcher can confirm what was heard.
  async function startRecording() {
    if (recording || transcribing || busy || !VOICE_SUPPORTED) return
    setVoiceErr(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        // Tear down the mic immediately so the OS indicator goes off.
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current,
                              { type: rec.mimeType || 'audio/webm' })
        chunksRef.current = []
        if (blob.size < 800) {
          setVoiceErr('Clip too short — hold the mic for at least a second.')
          return
        }
        sendVoice(blob)
      }
      recorderRef.current = rec
      rec.start()
      setRecording(true)
    } catch (e) {
      setVoiceErr(e?.message || 'Microphone permission denied.')
    }
  }

  function stopRecording() {
    const rec = recorderRef.current
    if (!rec) return
    setRecording(false)
    if (rec.state !== 'inactive') rec.stop()
    recorderRef.current = null
  }

  async function sendVoice(blob) {
    setTranscribing(true)
    setBusy(true)
    setHistory(h => [...h, { q: '🎙 …transcribing voice clip', pending: true,
                             voice: true }])
    try {
      const r = await copilotApi.voice({ audio: blob })
      setHistory(h => {
        const cp = [...h]
        const last = cp[cp.length - 1]
        if (last && last.pending) {
          cp[cp.length - 1] = {
            ...last, ...r,
            q: r.transcript || '(no speech detected)',
            pending: false,
            voice: true,
          }
        }
        return cp
      })
    } catch (err) {
      setHistory(h => {
        const cp = [...h]
        const last = cp[cp.length - 1]
        if (last && last.pending) {
          cp[cp.length - 1] = {
            ...last, pending: false, voice: true,
            q: '(voice clip)',
            answer: err?.response?.data?.detail || 'Voice request failed',
            error: 'voice_failed',
          }
        }
        return cp
      })
    } finally {
      setTranscribing(false)
      setBusy(false)
    }
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

      {/* Voice status / error pill */}
      {(recording || transcribing || voiceErr) && (
        <div className={`px-3 py-1.5 text-[11px] font-mono border-t border-line/50
                        ${voiceErr
                          ? 'bg-sig-critical/10 text-rose-200'
                          : recording
                            ? 'bg-rose-500/10 text-rose-200'
                            : 'bg-amber-400/10 text-amber-200'}`}>
          {voiceErr ?? (recording
            ? '● recording — release to send'
            : 'transcribing…')}
        </div>
      )}

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
        {VOICE_SUPPORTED && (
          <button
            type="button"
            disabled={busy && !recording}
            onMouseDown={startRecording}
            onMouseUp={stopRecording}
            onMouseLeave={() => recording && stopRecording()}
            onTouchStart={(e) => { e.preventDefault(); startRecording() }}
            onTouchEnd={(e) => { e.preventDefault(); stopRecording() }}
            title="Push and hold to talk"
            className={`px-3 py-2 rounded border transition-all
                       ${recording
                         ? 'bg-rose-500/20 border-rose-400 text-rose-200 animate-pulse'
                         : 'border-line/60 text-slate-300 hover:border-amber-400/50 hover:text-amber-200'}
                       disabled:opacity-40 disabled:cursor-not-allowed`}>
            {recording
              ? <Square className="w-4 h-4"/>
              : transcribing
                ? <Loader2 className="w-4 h-4 animate-spin"/>
                : <Mic className="w-4 h-4"/>}
          </button>
        )}
        <button type="submit" disabled={busy || !query.trim()}
                className="btn-danger px-3 py-2 disabled:opacity-40">
          {busy && !transcribing
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
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5 flex items-center gap-1.5">
          <span>you</span>
          {entry.voice && (
            <span className="inline-flex items-center gap-1 text-rose-300">
              <Mic className="w-2.5 h-2.5"/> voice
              {entry.transcribe_ms ? ` · ${entry.transcribe_ms}ms` : ''}
            </span>
          )}
        </div>
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
