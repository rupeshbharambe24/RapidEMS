/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans:  ['Manrope', 'system-ui', 'sans-serif'],
        mono:  ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Surfaces
        ink:       { 950: '#070912', 900: '#0a0e1a', 800: '#10162a', 700: '#1a2138', 600: '#252e4a' },
        line:      '#2a3450',                      // hairline borders
        // Severity / signals
        sig: {
          critical: '#ef4444',  // sev 1
          serious:  '#f97316',  // sev 2
          moderate: '#f59e0b',  // sev 3
          minor:    '#06b6d4',  // sev 4
          minimal:  '#10b981',  // sev 5
        },
      },
      boxShadow: {
        glow:        '0 0 0 1px rgba(34,211,238,.25), 0 0 24px -4px rgba(34,211,238,.35)',
        'glow-red':  '0 0 0 1px rgba(239,68,68,.45), 0 0 28px -2px rgba(239,68,68,.55)',
      },
      keyframes: {
        pulseRing: {
          '0%':   { transform: 'scale(0.75)', opacity: '0.85' },
          '80%':  { transform: 'scale(2.6)',  opacity: '0' },
          '100%': { transform: 'scale(2.6)',  opacity: '0' },
        },
        scanline: {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        fadeIn: {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to:   { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        pulseRing: 'pulseRing 1.6s cubic-bezier(0.19,1,0.22,1) infinite',
        scanline:  'scanline 7s linear infinite',
        fadeIn:    'fadeIn .25s ease-out both',
      },
    },
  },
  plugins: [],
}
