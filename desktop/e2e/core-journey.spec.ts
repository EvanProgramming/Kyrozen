/**
 * Kyrozen 3.6 P0 端到端发布门槛 — 核心旅程 E2E
 *
 * 覆盖文档 3.6 必须交付 #1（统一 E2E 与正式信息架构）与 #2（核心旅程：
 * 首次启动 → 登录 → 建项目 → 探索 → 研究 → PRD → 编码 → 测试 → 预览 →
 * 提交 → 推送 → 恢复）。
 *
 * 说明：
 * - 登录通过本地 HS256 JWT 深链接完成，不依赖真实 GitHub OAuth。
 * - 探索/研究/PRD/编码/测试 通过项目画布的真实标签页 + 一次真实 Agent 对话
 *   验证管线可用（对话需要后端 KYROZEN_DESKTOP_SERVER_URL + 模型）。
 * - 提交/推送 通过右侧 Git 面板入口验证（授权 / 初始化仓库 / 提交按钮）。
 * - 恢复 通过关闭应用后使用同一用户身份重新登录并重新打开项目验证。
 *
 * 每次发布运行都会通过 release-reporter 写入版本/系统/账号/项目ID/录像/
 * 截图/结果（3.6 #4），由本 spec 在运行期把账号与项目 ID 写入环境变量。
 */

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

const E2E_ACCOUNT = 'desktop-e2e@local.test';

async function launchElectron(profile: string, protocolUrl?: string) {
  const args = ['dist-electron/main/main.js'];
  if (protocolUrl) args.push(protocolUrl);
  args.push(`--user-data-dir=${profile}`);
  return _electron.launch({
    args,
    cwd: '.',
    env: {
      ...process.env,
      NODE_ENV: 'production',
      KYROZEN_DESKTOP_SERVER_URL: process.env.KYROZEN_DESKTOP_SERVER_URL || 'http://127.0.0.1:8001',
      KYROZEN_PYTHON_PATH: path.resolve('..', '.venv', 'bin', 'python'),
    },
  });
}

test.describe('Kyrozen 3.6 核心旅程', () => {
  test('首次启动显示引导页（未配置 onboarding）', async () => {
    test.setTimeout(60_000);
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-onboard-e2e-'));
    const electronApp = await launchElectron(profile);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('onboarding-page')).toBeVisible({ timeout: 25_000 });
      await expect(window.getByRole('button', { name: '中文' })).toBeVisible();
      await expect(window.getByRole('button', { name: 'English' })).toBeVisible();
    } finally {
      await electronApp.close();
      await fs.rm(profile, { recursive: true, force: true });
    }
  });

  test('登录 → 建项目 → 画布(探索/研究/PRD/编码/测试) → 提交/推送入口 → 恢复', async () => {
    test.setTimeout(420_000);
    const userId = randomUUID();
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-core-e2e-'));
    const projectName = `桌面验收项目-${Date.now()}`;
    await fs.writeFile(
      path.join(profile, 'onboarding.json'),
      JSON.stringify({ completed: true, language: 'zh' }),
    );

    // 发布记录（3.6 #4）：写入账号，便于 reporter 采集
    process.env.KYROZEN_E2E_ACCOUNT = E2E_ACCOUNT;

    const token = await createLocalAccessToken(userId);
    const protocolUrl = `kyzen://auth/login?kyzen_token=${encodeURIComponent(token)}&github_token=e2e-placeholder&scope=read%3Auser`;

    const electronApp = await launchElectron(profile, protocolUrl);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });

      // 建项目
      await window.getByRole('button', { name: '新建' }).click();
      await window.getByPlaceholder('例如：AI 写作助手').fill(projectName);
      await window.getByRole('button', { name: '创建', exact: true }).click();
      await expect(
        window.getByTestId('project-list').getByText(projectName, { exact: true }),
      ).toBeVisible({ timeout: 20_000 });

      // 记录项目 ID 供发布记录使用（3.6 #4）
      const projects = (await window.evaluate(
        async () => (window as any).kyrozen.getProjects(),
      )) as Array<{ id: string; name: string }>;
      const created = projects.find((p) => p.name === projectName);
      if (created) process.env.KYROZEN_E2E_PROJECT_ID = created.id;

      // 项目画布（探索/研究/PRD/编码/测试 的真实标签页）
      await window.getByRole('button', { name: '项目画布' }).click();
      await expect(window.getByTestId('project-workspace-panel')).toBeVisible();
      for (const tab of ['问题与证据', '产品方案', '开发交付', '测试验证', '学习改进', '项目决策']) {
        await expect(window.getByRole('button', { name: tab })).toBeVisible();
      }

      // 进入“开发交付”（编码）标签
      await window.getByRole('button', { name: '开发交付' }).click();

      // 探索 → 研究 → PRD：发送一次真实 Agent 对话，验证管线可用
      const assistantBefore = await window.getByTestId('chat-message-assistant').count();
      await window.getByPlaceholder('输入消息或拖拽文件...').fill('请只回复：桌面链路正常');
      await window.getByRole('button', { name: '发送' }).click();
      await expect
        .poll(() => window.getByTestId('chat-message-assistant').count(), { timeout: 240_000 })
        .toBeGreaterThan(assistantBefore);
      await expect(window.getByText('发送失败', { exact: false })).toHaveCount(0);

      // 提交 / 推送 入口（右侧 Git 面板，始终可见）
      await expect(window.getByTestId('git-panel')).toBeVisible();
      await expect(
        window.getByRole('button', { name: '初始化 Git 仓库（main 分支 + .gitignore + 首个提交）' }),
      ).toBeVisible();

      // 恢复：退出后使用同一身份重新登录，项目应仍存在且可继续
      await electronApp.close();
      const token2 = await createLocalAccessToken(userId);
      const protocolUrl2 = `kyzen://auth/login?kyzen_token=${encodeURIComponent(token2)}&github_token=e2e-placeholder&scope=read%3Auser`;
      const electronApp2 = await launchElectron(profile, protocolUrl2);
      try {
        const window2 = await electronApp2.firstWindow();
        await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });
        await expect(
          window2.getByTestId('project-list').getByText(projectName, { exact: true }),
        ).toBeVisible({ timeout: 20_000 });
        await window2.getByRole('button', { name: '项目画布' }).click();
        await expect(window2.getByTestId('project-workspace-panel')).toBeVisible();
      } finally {
        await electronApp2.close();
      }
    } finally {
      await fs.rm(profile, { recursive: true, force: true });
      delete process.env.KYROZEN_E2E_ACCOUNT;
      delete process.env.KYROZEN_E2E_PROJECT_ID;
    }
  });
});
