import { createHmac, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { expect, _electron, test } from '@playwright/test';

function base64Url(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

async function createLocalAccessToken(userId: string): Promise<string> {
  const envFile = await fs.readFile(path.resolve('..', '.env'), 'utf-8');
  const secret = envFile.match(/^SUPABASE_JWT_SECRET=(.+)$/m)?.[1]?.trim();
  if (!secret) throw new Error('SUPABASE_JWT_SECRET is required for the local desktop journey');
  const now = Math.floor(Date.now() / 1000);
  const header = base64Url({ alg: 'HS256', typ: 'JWT' });
  const payload = base64Url({
    sub: userId,
    email: 'desktop-e2e@local.test',
    aud: 'authenticated',
    iat: now,
    exp: now + 3600,
    user_metadata: { name: 'Desktop E2E' },
  });
  const signature = createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url');
  return `${header}.${payload}.${signature}`;
}

test('authenticated desktop can create and open a real project workspace', async () => {
  test.setTimeout(180_000);
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-core-e2e-'));
  const projectName = `桌面修复验收项目-${Date.now()}`;
  await fs.writeFile(path.join(profile, 'onboarding.json'), JSON.stringify({ completed: true, language: 'zh' }));
  const token = await createLocalAccessToken(randomUUID());
  const protocolUrl = `kyrozen://auth/login?kyrozen_token=${encodeURIComponent(token)}&github_token=e2e-placeholder&scope=read%3Auser`;
  const electronApp = await _electron.launch({
    args: ['dist-electron/main/main.js', protocolUrl, `--user-data-dir=${profile}`],
    cwd: '.',
    env: {
      ...process.env,
      NODE_ENV: 'production',
      KYROZEN_DESKTOP_SERVER_URL: 'http://127.0.0.1:8001',
      KYROZEN_PYTHON_PATH: path.resolve('..', '.venv', 'bin', 'python'),
    },
  });

  try {
    const window = await electronApp.firstWindow();
    await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 20_000 });

    await window.getByRole('button', { name: '新建' }).click();
    await window.getByPlaceholder('例如：AI 写作助手').fill(projectName);
    await window.getByRole('button', { name: '创建', exact: true }).click();
    await expect(window.getByTestId('project-list').getByText(projectName, { exact: true })).toBeVisible({ timeout: 15_000 });

    await window.getByRole('button', { name: '项目画布' }).click();
    await expect(window.getByTestId('project-workspace-panel')).toBeVisible();
    await expect(window.getByRole('button', { name: '采购 / Maker' })).toBeVisible();
    await expect(window.getByRole('button', { name: '决策中心' })).toBeVisible();
    await window.getByRole('button', { name: '关闭' }).click();

    await window.reload({ waitUntil: 'domcontentloaded', timeout: 15_000 });
    await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 15_000 });
    await expect(window.getByTestId('project-list').getByText(projectName, { exact: true })).toBeVisible();

    const assistantMessages = window.getByTestId('chat-message-assistant');
    const assistantCountBefore = await assistantMessages.count();
    await window.getByPlaceholder('输入消息或拖拽文件...').fill('请只回复：桌面链路正常');
    await window.getByRole('button', { name: '发送' }).click();
    await expect.poll(() => assistantMessages.count(), { timeout: 120_000 }).toBeGreaterThan(assistantCountBefore);
    await expect(window.getByText('发送失败', { exact: false })).toHaveCount(0);
  } finally {
    await electronApp.close();
    await fs.rm(profile, { recursive: true, force: true });
  }
});
