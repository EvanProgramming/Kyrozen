import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  // 3.6 #4: 每次发布运行保存录像/截图/结果到 e2e/release-runs/
  reporter: [
    ['list'],
    ['./e2e/release-reporter.ts'],
  ],
  use: {
    // 始终记录录像（发布门槛要求可回放），失败用例额外截图。
    video: 'on',
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
