import { defineConfig } from '@playwright/test';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

export default defineConfig({
  testDir: '.',
  testMatch: ['*.spec.mjs'],
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:4173'
  },
  webServer: {
    command: 'python -m http.server 4173 -d frontend',
    cwd: repoRoot,
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 30000
  }
});
