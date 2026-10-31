import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue(), vueJsx()],
  test: {
    environment: 'node',
    include: ['**/*.test.ts'],
    exclude: ['**/node_modules/**', '**/.nuxt/**'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'app'),
      '~': resolve(__dirname, 'app'),
    },
  },
})
