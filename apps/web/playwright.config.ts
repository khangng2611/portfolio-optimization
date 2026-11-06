import { defineConfig } from '@playwright/test';

// This gate always uses the real disposable Compose stack. No dev server/mocks.
export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.e2e.ts',
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 180_000,
  globalTimeout: 600_000,
  expect: { timeout: 20_000 },
  outputDir: '../../output/playwright/private-results',
  reporter: [['./tests/browser/safe-reporter.ts']],
  use: {
    baseURL: 'http://localhost:3000',
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: 'off',
    video: 'off',
    screenshot: 'off',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
});
