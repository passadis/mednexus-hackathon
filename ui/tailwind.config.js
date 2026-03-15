/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // MedNexus brand palette – Dark Medical
        brand: {
          50: '#eef7ff',
          100: '#d9edff',
          200: '#bce0ff',
          300: '#8eceff',
          400: '#59b2ff',
          500: '#3391ff',
          600: '#1b70f5',
          700: '#145ae1',
          800: '#1749b6',
          900: '#19408f',
          950: '#142857',
        },
        medical: {
          green: '#34d399',
          red: '#f87171',
          amber: '#fbbf24',
          blue: '#60a5fa',
        },
        surface: {
          0: '#0a0f1e',
          1: '#111827',
          2: '#1a2236',
          3: '#222d44',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'thinking': 'thinking 1.5s ease-in-out infinite',
        'glow': 'glow 2s ease-in-out infinite',
        'shimmer': 'shimmer 2.5s linear infinite',
      },
      keyframes: {
        thinking: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 15px rgba(59, 130, 246, 0.15)' },
          '50%': { boxShadow: '0 0 30px rgba(59, 130, 246, 0.25)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};
