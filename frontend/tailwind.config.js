/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Light, low-saturation palette. No dark mode by design.
        canvas: '#f7f8fa',
        surface: '#ffffff',
        line: '#e6e8ee',
        ink: {
          900: '#111827',
          700: '#374151',
          500: '#6b7280',
          400: '#9ca3af',
        },
        accent: {
          50: '#eef4ff',
          100: '#dbe7ff',
          200: '#bdd2ff',
          400: '#6b95f5',
          500: '#3f6ee0',
          600: '#2f56b8',
        },
        good: { 50: '#ecfdf5', 200: '#a7f3d0', 500: '#059669', 700: '#047857' },
        warn: { 50: '#fffbeb', 200: '#fde68a', 500: '#d97706', 700: '#b45309' },
        bad: { 50: '#fef2f2', 200: '#fecaca', 500: '#dc2626', 700: '#b91c1c' },
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(17, 24, 39, 0.04), 0 8px 24px -12px rgba(17, 24, 39, 0.12)',
        lift: '0 2px 4px rgba(17, 24, 39, 0.05), 0 16px 40px -20px rgba(17, 24, 39, 0.2)',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
      maxWidth: {
        content: '1180px',
      },
      keyframes: {
        'fade-rise': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-rise': 'fade-rise 220ms ease-out both',
      },
    },
  },
  plugins: [],
}
