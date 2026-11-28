import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const web = fileURLToPath(new URL('../../', import.meta.url));
export default defineConfig({
  testDir: '.', testMatch: '*.e2e.ts', workers: 1, timeout: 90_000,
  outputDir: '../../../../output/playwright/paper-fixture',
  use: { baseURL: 'http://127.0.0.1:32158', viewport: { width: 390, height: 844 }, trace: 'off' },
  webServer: [
    { cwd: web, command: 'cp -R .next/static .next/standalone/.next/ && cp -R public .next/standalone/ && node .next/standalone/server.js', env: { HOSTNAME: '127.0.0.1', PORT: '32158' }, url: 'http://127.0.0.1:32158/health/live' },
    { cwd: web, command: '../../.venv-software/bin/python tests/paper-browser/service.py', env: { PYTHONPATH: '../../tests/software' }, url: 'http://127.0.0.1:32159/scenario' },
  ],
});
