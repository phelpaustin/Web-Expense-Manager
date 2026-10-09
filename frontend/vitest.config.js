import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

// Test-only settings; `vite build` and `vite dev` ignore this file.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{js,jsx}'],
    },
  }),
)
