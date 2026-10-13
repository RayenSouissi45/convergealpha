import { defineConfig, devices } from '@playwright/test'

// Runs against the production build (`npm run build` first) served by `vite preview`.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'github' : 'list',
  // Service workers are blocked so request interception in tests sees every fetch.
  // 127.0.0.1, not localhost: on Windows localhost may resolve to IPv6 while the browser uses IPv4.
  use: { baseURL: 'http://127.0.0.1:4173/', serviceWorkers: 'block' },
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'] } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173/',
    reuseExistingServer: !process.env.CI,
  },
})
