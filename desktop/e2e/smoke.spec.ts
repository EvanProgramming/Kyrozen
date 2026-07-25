import { test, expect, _electron } from '@playwright/test';

test.describe('Kyrozen Desktop Smoke', () => {
  test('launches main window with Kyrozen title', async () => {
    const electronApp = await _electron.launch({
      args: ['dist-electron/main/main.js'],
      cwd: '.',
    });

    try {
      const window = await electronApp.firstWindow();
      await expect(window).toHaveTitle(/Kyrozen/i);
      // The app should render either the login page or onboarding.
      await expect(window.locator('text=Kyrozen').first()).toBeVisible();
    } finally {
      await electronApp.close();
    }
  });

  test('settings page opens when triggered', async () => {
    const electronApp = await _electron.launch({
      args: ['dist-electron/main/main.js'],
      cwd: '.',
    });

    try {
      const window = await electronApp.firstWindow();
      await expect(window.locator('text=Kyrozen').first()).toBeVisible();
      // When already logged in/onboarded, the settings button is available.
      const settingsButton = window.locator('text=设置');
      if (await settingsButton.isVisible().catch(() => false)) {
        await settingsButton.click();
        await expect(window.locator('text=完全信任模式')).toBeVisible();
      }
    } finally {
      await electronApp.close();
    }
  });
});
