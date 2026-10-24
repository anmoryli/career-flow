const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser', timeout: 45000, workers: 1,
  outputDir: 'output/browser',
  reporter: [['list'], ['html', { outputFolder: 'output/browser-report', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8011', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: 'uv run python scripts/e2e-server.py', url: 'http://127.0.0.1:8011/health/live', reuseExistingServer: false, timeout: 30000 },
  projects: [{ name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 1000 } } },
    { name: 'tablet', use: { browserName: 'chromium', viewport: { width: 820, height: 1180 } } },
    { name: 'mobile', use: { browserName: 'chromium', viewport: { width: 390, height: 844 } } }],
});
