import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { SUPPORTED_LANGS } from '../i18n/index.js'

export default function LangPicker({ compact = false }) {
  const { i18n, t } = useTranslation()

  function change(e) {
    const code = e.target.value
    i18n.changeLanguage(code)
    try { localStorage.setItem('rapidems.lang', code) } catch {}
  }

  return (
    <label className={`inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400 ${compact ? '' : 'border border-line/40 rounded px-2 py-1'}`}>
      <Globe className="w-3 h-3"/>
      {!compact && <span className="hidden sm:inline">{t('lang_picker')}</span>}
      <select value={i18n.resolvedLanguage || i18n.language || 'en'}
              onChange={change}
              className="bg-transparent border-none outline-none cursor-pointer normal-case text-xs">
        {SUPPORTED_LANGS.map(l => (
          <option key={l.code} value={l.code} className="bg-ink-900">
            {l.label}
          </option>
        ))}
      </select>
    </label>
  )
}
