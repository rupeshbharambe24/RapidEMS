export default function KPICard({ label, value, hint, accent = 'cyan', icon: Icon }) {
  const accents = {
    cyan:    'text-cyan-300 border-cyan-400/30',
    red:     'text-sig-critical border-sig-critical/30',
    amber:   'text-sig-moderate border-sig-moderate/30',
    emerald: 'text-sig-minimal border-sig-minimal/30',
    slate:   'text-slate-300 border-line',
  }[accent]

  return (
    <div className={`card p-4 relative overflow-hidden border-l-2 ${accents}`}>
      {/* Subtle corner mark */}
      <div className="absolute top-2 right-2 text-[9px] font-mono uppercase tracking-widest text-slate-600">●</div>
      <div className="flex items-start gap-3">
        {Icon && <Icon className="w-4 h-4 mt-0.5 opacity-70" strokeWidth={2.2}/>}
        <div className="min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-slate-400">{label}</div>
          <div className="font-mono text-2xl mt-1.5 tabular-nums">{value}</div>
          {hint && <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>}
        </div>
      </div>
    </div>
  )
}
