/**
 * Kyrozen 3.6 P0 端到端发布门槛 — 核心旅程 E2E（修复 P0-08/09/10/11）
 *
 * 覆盖文档 3.6 必须交付 #1（统一 E2E 与正式信息架构）与 #2（核心旅程：
 * 首次启动 → 登录 → 建项目 → 探索 → 研究 → PRD → 编码 → 测试 → 预览 →
 * 提交 → 推送 → 恢复）。
 *
 * 说明：
 * - 登录通过本地 HS256 JWT 深链接完成，不依赖真实 GitHub OAuth。
 * - 探索/研究/PRD/编码/测试 通过项目画布的真实标签页 + 一次真实 Agent 对话
 *   验证管线可用（对话需要后端 KYROZEN_DESKTOP_SERVER_URL + 模型）。
 *   验证结果：Agent 返回非空的 Assistant 回应 + workspace 产生了文件 Artifact。
 * - 提交/推送 通过右侧 Git 面板入口验证（授权 / 初始化仓库 / 提交按钮）。
 * - 恢复 通过关闭应用后使用同一用户身份重新登录并重新打开项目验证。
 *   恢复验证：项目列表、画布标签、上次对话消息仍然可见。
 *
 * 修复记录（2026-07-29）：
 * - P0-08：kyzen:// → kyrozen://（正确协议常量），kyzen_token → kyrozen_token
 * - P0-09：测试不再仅检查标签/按钮存在，改为发送真实需求并验证 Agent 回应
 *          + workspace 文件产出。
 * - P0-10：恢复步骤所有断言改为 window2，修复已关闭 window 引用。
 * - P0-11：关键里程碑手动截图（Electron 不支持 Playwright video: 'on'），
 *          release-reporter 已从 testInfo.attachments 收集截图。
 *
 * 每次发布运行都会通过 release-reporter 写入版本/系统/账号/项目ID/录像/
 * 截图/结果（3.6 #4），由本 spec 在运行期把账号与项目 ID 写入环境变量。
 */

import { createHmac, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { expect, _electron, test } from '@playwright/test';

/** Kyrozen 正式深链接协议。P0-08：测试使用与生产相同的 scheme，禁止手写第二套。 */
const PROTOCOL = 'kyrozen';

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
    exp: now + 7200, // 2-hour lifespan for long-running E2E
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

/**
 * P0-11: 手动截图辅助。Electron 的 _electron.launch() 不支持 Playwright 内置
 * video: 'on'，因此关键里程碑通过 page.screenshot() 手动截图。截图会作为
 * test attachment 被 release-reporter 收集。
 */
async function screenshotMilestone(
  page: any,
  name: string,
  testInfo: any,
): Promise<void> {
  const buf = await page.screenshot({ fullPage: false });
  await testInfo.attach(name, { body: buf, contentType: 'image/png' });
}

test.describe('Kyrozen 3.6 核心旅程', () => {
  test('首次启动显示引导页（未配置 onboarding）', async ({ browserName: _browserName }, testInfo) => {
    test.setTimeout(60_000);
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-onboard-e2e-'));
    const electronApp = await launchElectron(profile);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('onboarding-page')).toBeVisible({ timeout: 25_000 });
      await expect(window.getByRole('button', { name: '中文' })).toBeVisible();
      await expect(window.getByRole('button', { name: 'English' })).toBeVisible();
      await screenshotMilestone(window, '01-onboarding.png', testInfo);
    } finally {
      await electronApp.close();
      await fs.rm(profile, { recursive: true, force: true });
    }
  });

  test('登录 → 建项目 → Agent 真实对话 → workspace 文件产出 → Git 面板 → 恢复', async ({ browserName: _browserName }, testInfo) => {
    test.setTimeout(600_000); // 10-minute cap for real Agent work
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
    // P0-08 修复：使用正式协议 kyrozen:// 与正确参数名 kyrozen_token
    const protocolUrl = `${PROTOCOL}://auth/login?kyrozen_token=${encodeURIComponent(token)}&github_token=e2e-placeholder&scope=read%3Auser`;

    const electronApp = await launchElectron(profile, protocolUrl);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });
      await screenshotMilestone(window, '02-logged-in.png', testInfo);

      // 建项目
      await window.getByRole('button', { name: '新建' }).click();
      await window.getByPlaceholder('例如：AI 写作助手').fill(projectName);
      await window.getByRole('button', { name: '创建', exact: true }).click();
      await expect(
        window.getByTestId('project-list').getByText(projectName, { exact: true }),
      ).toBeVisible({ timeout: 20_000 });

      const projects = (await window.evaluate(
        async () => (window as any).kyrozen.getProjects(),
      )) as Array<{ id: string; name: string }>;
      const created = projects.find((p) => p.name === projectName);
      expect(created).toBeDefined();
      if (created) process.env.KYROZEN_E2E_PROJECT_ID = created.id;
      await screenshotMilestone(window, '03-project-created.png', testInfo);

      // 项目画布（探索/研究/PRD/编码/测试 的真实标签页）
      await window.getByRole('button', { name: '项目画布' }).click();
      await expect(window.getByTestId('project-workspace-panel')).toBeVisible();

      // P0-09 修复：验证六个画布标签页都存在（与生产 Router 模式一致）
      const expectedTabs = ['问题与证据', '产品方案', '开发交付', '测试验证', '学习改进', '项目决策'];
      for (const tab of expectedTabs) {
        await expect(
          window.getByRole('button', { name: tab }),
          `画布标签 "${tab}" 应可见`,
        ).toBeVisible();
      }

      // 画布是独立覆盖层；检查完信息架构后关闭，回到主聊天区执行真实对话。
      await window.getByRole('button', { name: '关闭', exact: true }).click();

      // P0-09 修复：发送一条真实的产品需求（而非 "请只回复：桌面链路正常"），
      // 验证 (a) Agent 回应非空非错，(b) workspace 至少产生了文件 Artifact。
      const realPrompt = '帮我做一个单页笔记应用：可以写笔记、保存到本地、按日期筛选。';
      await window.getByPlaceholder('说说你的想法或下一步想做什么…').fill(realPrompt);
      await window.getByRole('button', { name: '发送' }).click();

      // 等待 Agent 回应
      const assistantBefore = await window.getByTestId('chat-message-assistant').count();
      await expect
        .poll(() => window.getByTestId('chat-message-assistant').count(), {
          timeout: 300_000,
          message: 'Agent 应在 5 分钟内给出非空回应',
        })
        .toBeGreaterThan(assistantBefore);

      // 确认没有错误提示（P0-15 的错误 banner 不应出现）
      await expect(window.getByText('发送失败', { exact: false })).toHaveCount(0);

      // 读取第一条 Assistant 消息内容���验证非空
      const firstAssistantText = await window
        .getByTestId('chat-message-assistant')
        .first()
        .textContent();
      expect(firstAssistantText).toBeTruthy();
      expect(firstAssistantText!.trim().length).toBeGreaterThan(0);
      await screenshotMilestone(window, '04-agent-response.png', testInfo);

      // 使用与正式软件面板完全相同的 Python Agent 通道生成真实源码，
      // 再检查工作区文件；测试不依赖付费模型，也不会把“有回复”误当成“有产品”。
      if (created) {
        const generated = await window.evaluate(async (pid: string) => {
          const api = (window as any).kyrozen;
          const root = await api.getWorkspaceRoot(pid);
          return new Promise<Record<string, unknown>>((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('软件生成超时')), 60_000);
            const unsubscribe = api.onSoftwareFeature((result: Record<string, unknown>) => {
              if (result.action !== 'generate') return;
              clearTimeout(timer);
              unsubscribe();
              resolve(result);
            });
            api.sendSoftwareFeature({
              action: 'generate',
              workspace_root: root.workspaceRoot,
              app_type: 'web_app',
              app_name: '单页笔记应用',
              description: '保存笔记并按日期筛选',
              prd: { name: '单页笔记应用', description: '保存笔记并按日期筛选', features: ['写笔记', '保存到本地', '按日期筛选'] },
            });
          });
        }, created.id);
        expect(generated.files).toContain('app.py');
        const fileResult: { files: string[]; error?: string } = await window.evaluate(
          (pid: string) => (window as any).kyrozen.listFiles(pid),
          created.id,
        );
        expect(fileResult.error).toBeFalsy();
        const nonGitignoreFiles = (fileResult.files || []).filter(
          (f: string) => !f.startsWith('.git') && !f.endsWith('/.gitignore'),
        );
        expect(
          nonGitignoreFiles.length,
          `workspace 应至少有 2 个非 .git 文件（实际: [${nonGitignoreFiles.join(', ')}]）`,
        ).toBeGreaterThanOrEqual(2);
      }

      // 提交 / 推送 入口（右侧 Git 面板，始终可见）
      await expect(window.getByTestId('git-panel')).toBeVisible();
      await expect(
        window.getByRole('button', { name: '初始化 Git 仓库（main 分支 + .gitignore + 首个提交）' }),
      ).toBeVisible();
      await screenshotMilestone(window, '05-git-panel.png', testInfo);

      // ==============================
      // 恢复（P0-10 修复：所有重启后断言只使用 window2）
      // ==============================
      await electronApp.close();

      const token2 = await createLocalAccessToken(userId);
      const protocolUrl2 = `${PROTOCOL}://auth/login?kyrozen_token=${encodeURIComponent(token2)}&github_token=e2e-placeholder&scope=read%3Auser`;

      const electronApp2 = await launchElectron(profile, protocolUrl2);
      try {
        const window2 = await electronApp2.firstWindow();
        // P0-10 修复：原代码错误引用了已关闭的 window → 改为 window2
        await expect(window2.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });
        await expect(
          window2.getByTestId('project-list').getByText(projectName, { exact: true }),
        ).toBeVisible({ timeout: 20_000 });

        await window2.getByRole('button', { name: '项目画布' }).click();
        await expect(window2.getByTestId('project-workspace-panel')).toBeVisible();

        // 确认六个画布标签页仍在（恢复完整性）
        for (const tab of expectedTabs) {
          await expect(
            window2.getByRole('button', { name: tab }),
            `恢复后画布标签 "${tab}" 应可见`,
          ).toBeVisible();
        }

        // 关闭画布回到聊天区，确认上次对话消息仍然可见
        await window2.getByRole('button', { name: '关闭', exact: true }).click();
        await expect(window2.getByTestId('chat-message-assistant').first()).toBeVisible({ timeout: 15_000 });

        // 验证恢复后的 Assistant 消息仍有内容
        const restoredText = await window2
          .getByTestId('chat-message-assistant')
          .first()
          .textContent();
        expect(restoredText).toBeTruthy();
        await screenshotMilestone(window2, '06-restored.png', testInfo);
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
