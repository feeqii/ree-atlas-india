import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/app/**/*.{ts,tsx}',
    './src/components/**/*.{ts,tsx}'
  ],
  theme: {
    extend: {
      colors: {
        ink: '#121416',
        mist: '#f3f5f7',
        reef: '#0f766e',
        sand: '#cbb08a'
      },
      boxShadow: {
        soft: '0 6px 20px rgba(15, 23, 42, 0.12)'
      }
    }
  },
  plugins: []
}

export default config
