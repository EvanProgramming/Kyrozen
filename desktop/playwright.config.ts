import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  webServer: {
    command: '../.venv/bin/python e2e/local-server.py',
    url: 'http://127.0.0.1:8001/api/health',
    timeout: 30_000,
    reuseExistingServer: false,
  },
  // 3.6 #4: 每次发布运行保存录像/截图/结果到 e2e/release-runs/
  reporter: [
    ['list'],
    ['./e2e/release-reporter.ts'],
  ],
  use: {
    // _electron.launch() 不支持 Playwright 内置 video 录制。
    // 关键里程碑通过 page.screenshot() 手动截图，由 release-reporter 收集。
    // trace 和失败截图仍通过 Playwright 内置机制产生。
    trace: 'on',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'electron',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
