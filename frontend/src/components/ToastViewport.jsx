import { useUiStore } from '../store/ui.js'
import { X, AlertTriangle, Info, CheckCircle2 } from 'lucide-react'

const KIND_STYLES = {
  critical: { icon: AlertTriangle, klass: 'border-sig-critical/60 bg-sig-critical/15' },
  info:     { icon: Info,          klass: 'border-cyan-400/60 bg-cyan-400/10'        },
  success:  { icon: CheckCircle2,  klass: 'border-sig-minimal/60 bg-sig-minimal/15'  },
}

export default function ToastViewport() {
  const toasts  = useUiStore(s => s.toasts)
  const dismiss = useUiStore(s => s.dismissToast)
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(t => {
        const { icon: Icon, klass } = KIND_STYLES[t.kind] || KIND_STYLES.info
        return (
          <div key={t.id}
            className={`pointer-events-auto flex items-start gap-3 backdrop-blur
                        border rounded-lg px-3.5 py-2.5 shadow-2xl animate-fadeIn ${klass}`}>
            <Icon className="w-4 h-4 mt-0.5 shrink-0" strokeWidth={2.4}/>
            <div className="text-sm flex-1">{t.message}</div>
            <button onClick={() => dismiss(t.id)} className="text-slate-400 hover:text-slate-200">
              <X className="w-3.5 h-3.5"/>
            </button>
          </div>
        )
      })}
    </div>
  )
}
