/**
 * i18next setup. English source-of-truth; HI/MR/TA/BN mostly translated
 * with a graceful fallback to English for any missing keys.
 *
 * Detection order: localStorage → browser language → English. The picker
 * component (`LangPicker`) writes the user's choice back to localStorage.
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import hi from './locales/hi.json'
import mr from './locales/mr.json'
import ta from './locales/ta.json'
import bn from './locales/bn.json'

export const SUPPORTED_LANGS = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'mr', label: 'मराठी' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'bn', label: 'বাংলা' },
]

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
      mr: { translation: mr },
      ta: { translation: ta },
      bn: { translation: bn },
    },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGS.map(l => l.code),
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'rapidems.lang',
    },
    react: { useSuspense: false },
  })

export default i18n
