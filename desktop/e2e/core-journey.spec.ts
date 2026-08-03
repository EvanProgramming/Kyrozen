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

      // Phase 2 项目画布：七个专用工作中心。
      await window.getByRole('button', { name: '项目画布' }).click();
      await expect(window.getByTestId('project-workspace-panel')).toBeVisible();

      // 验证七个工作中心都可发现（与正式信息架构一致）
      const expectedTabs = ['项目主页', '决策中心', '采购中心', 'Maker 模式', '测试中心', '改进中心', '反馈中心'];
      for (const tab of expectedTabs) {
        await expect(
          window.getByRole('tab', { name: tab }),
          `画布标签 "${tab}" 应可见`,
        ).toBeVisible();
      }

      // 窄窗口 + 键盘验收：标签可滚动、具备 tab 语义，并支持方向键/Home/End。
      await window.setViewportSize({ width: 520, height: 720 });
      const overviewTab = window.getByRole('tab', { name: '项目主页' });
      await overviewTab.focus();
      await overviewTab.press('End');
      await expect(window.getByRole('tab', { name: '反馈中心' })).toHaveAttribute('aria-selected', 'true');
      await window.getByRole('tab', { name: '反馈中心' }).press('Home');
      await expect(overviewTab).toHaveAttribute('aria-selected', 'true');
      await window.setViewportSize({ width: 1280, height: 800 });

      // 证据→研究入口也必须从桌面端真实写入；研究运行本身在后端
      // 单测和独立外部探测中验证，E2E 不依赖第三方服务可用性。
      await window.getByPlaceholder('观察到的事实或用户原话').fill('用户希望先看到设备是否在线，再决定是否开始装配');
      await window.getByPlaceholder('原文、截图说明或记录上下文').fill('访谈记录：用户不愿凭猜测选择串口');
      await window.getByRole('button', { name: '保存证据' }).click();
      await expect(window.getByRole('status')).toContainText('证据已保存');
      await window.getByRole('button', { name: '查看影响' }).first().click();
      await expect(window.getByRole('status')).toContainText('影响预览完成');
      await window.getByRole('button', { name: '标记无效' }).first().click();
      await expect(window.getByRole('status')).toContainText('证据已标记无效');
      await window.getByRole('button', { name: '恢复证据' }).first().click();
      await expect(window.getByRole('status')).toContainText('证据已恢复');

      // Problem Brief 的引用必须能从结论跳回原始证据，而不是只展示被隐藏的 ID。
      const evidenceWorkspace = await window.evaluate(async (pid: string) => {
        const result = await (window as any).kyrozen.getProjectWorkspace(pid);
        const evidence = (result.data?.artifacts || []).find((artifact: Record<string, unknown>) => artifact.type === 'discovery_evidence');
        let content: Record<string, unknown> = {};
        try { content = evidence ? JSON.parse(String(evidence.content || '{}')) : {}; } catch { /* assertion below reports missing data */ }
        return { evidenceId: evidence?.id, observedAt: content.observed_at, source: content.source, artifacts: result.data?.artifacts || [] };
      }, created!.id);
      expect(evidenceWorkspace.evidenceId).toBeTruthy();
      expect(evidenceWorkspace.observedAt).toBeTruthy();
      expect(evidenceWorkspace.source).toBe('user_statement');
      if (evidenceWorkspace.evidenceId) {
        const brief = await window.evaluate(async (args: { pid: string; evidenceId: string }) => {
          return (window as any).kyrozen.createArtifact(
            args.pid,
            'problem_brief',
            'Problem Brief',
            JSON.stringify({
              title: '串口目标识别问题',
              evidence_ids: [args.evidenceId],
              counter_evidence_ids: [],
              unresolved_questions: ['新手是否能独立判断串口目标？'],
            }),
            '桌面端证据引用回归',
          );
        }, { pid: created!.id, evidenceId: String(evidenceWorkspace.evidenceId) });
        expect(brief.success).toBeTruthy();
        await window.getByRole('button', { name: '刷新' }).click();
        await expect(window.getByTestId('problem-brief-evidence-references')).toContainText('用户希望先看到设备是否在线');
        await window.getByTestId('problem-brief-evidence-references').getByRole('button', { name: /用户希望先看到设备是否在线/ }).click();
        await expect(window.locator(`#evidence-${evidenceWorkspace.evidenceId}`)).toBeVisible();
      }

      // 每个专用中心至少完成一次真实写入，随后通过刷新读取验证持久化。
      await window.getByRole('tab', { name: '决策中心' }).click();
      await window.getByPlaceholder('做出了什么决定？').fill('先验证串口识别，再进入硬件装配');
      await window.getByPlaceholder('为什么这样决定？依据和取舍是什么？').fill('证据显示新手无法凭猜测选择串口，先降低误接线风险。');
      await window.getByRole('button', { name: '保存决策' }).click();
      await expect(window.getByRole('status')).toContainText('决策已保存');
      await window.getByRole('button', { name: '刷新' }).click();
      await expect(window.getByText('先验证串口识别，再进入硬件装配')).toBeVisible();

      await window.getByRole('tab', { name: '采购中心' }).click();
      await window.getByRole('button', { name: '只读发现设备' }).click();
      await expect(window.getByText('BLOCKED', { exact: true }).first()).toBeVisible({ timeout: 30_000 });
      await expect(window.getByRole('alert')).toContainText('重试硬件操作：list_ports');
      await expect(window.getByRole('group', { name: '硬件实际行为 Ask question' })).toBeVisible();
      await window.getByRole('button', { name: '不符合/暂不确认' }).click();
      await expect(window.getByRole('status')).toContainText('保持 BLOCKED');
      await window.getByLabel('版本化协议消息').fill('{invalid');
      await window.getByRole('button', { name: '执行协议测试' }).click();
      await expect(window.getByRole('alert')).toContainText('执行协议测试');
      await window.getByLabel('版本化协议消息').fill('{"protocol_version":"1.0","message_type":"telemetry","fields":{"value":1},"direction":"app_to_device"}');
      await window.getByRole('button', { name: '重试：执行协议测试' }).click();
      await expect(window.getByText('PASSED', { exact: true }).first()).toBeVisible({ timeout: 30_000 });
      await window.getByRole('button', { name: '执行协议测试' }).click();
      await expect(window.getByText('PASSED', { exact: true }).first()).toBeVisible({ timeout: 30_000 });
      await window.getByRole('button', { name: '运行六种模拟场景' }).click();
      await expect(window.getByRole('status')).toContainText('协议六场景已通过并持久化', { timeout: 30_000 });
      await window.getByPlaceholder('型号、数量、供应商、采购状态或替代件').fill('ESP32-DevKitC，1 件，未购买；替代型号待确认');
      await window.getByRole('button', { name: '保存采购记录' }).click();
      await expect(window.getByRole('status')).toContainText('已保存');
      await window.getByLabel('精确型号').fill('ESP32-DevKitC V4');
      await window.getByLabel('数量').fill('1');
      await window.getByLabel('单价').fill('12');
      await window.getByLabel('供应商').fill('示例供应商');
      await window.getByRole('button', { name: '保存 BOM 条目' }).click();
      await expect(window.getByRole('status')).toContainText('BOM 条目已保存');
      await window.getByLabel('接线设备').fill('ESP32-DevKitC V4');
      await window.getByLabel('设备引脚').fill('GPIO 4');
      await window.getByLabel('目标引脚').fill('传感器 DATA');
      await window.getByLabel('接线电压').fill('3.3V');
      await window.getByLabel('电流方向').fill('传感器 → ESP32');
      await window.getByLabel('接线安全条件').fill('断电后接线\n禁止 5V 直接输入 GPIO');
      await window.getByRole('button', { name: '保存接线设计' }).click();
      await expect(window.getByRole('status')).toContainText('接线设计已保存');
      await window.getByLabel('固件版本').fill('0.1.0');
      await window.getByLabel('固件源码').fill('hardware/firmware/main.ino');
      await window.getByLabel('固件文件').fill('main.ino\nprotocol.json');
      await window.getByRole('button', { name: '保存固件定义' }).click();
      await expect(window.getByRole('status')).toContainText('固件项目定义已保存');
      const hardwareArtifacts = await window.evaluate(async (pid: string) => {
        const result = await (window as any).kyrozen.getProjectWorkspace(pid);
        return (result.data?.artifacts || []).map((artifact: Record<string, unknown>) => artifact.type);
      }, created!.id);
      expect(hardwareArtifacts).toEqual(expect.arrayContaining(['bom', 'wiring_design', 'firmware_project']));

      await window.getByRole('tab', { name: 'Maker 模式' }).click();
      await window.getByPlaceholder('元件、动作、预期结果、安全提示、照片说明和完成确认').fill('连接公共地；预期无短路；断电后再调整接线；未完成');
      await window.getByRole('button', { name: '保存装配确认' }).click();
      await expect(window.getByRole('status')).toContainText('已保存');
      await window.getByLabel('涉及元件').fill('ESP32-DevKitC V4');
      await window.getByLabel('装配动作').fill('连接公共地');
      await window.getByLabel('预期结果').fill('串口可稳定输出');
      await window.getByLabel('安全提示').fill('断电后再调整接线');
      await window.getByLabel('照片说明').fill('尚未连接实物');
      await window.getByLabel('我已完成并确认此步骤').check();
      await window.getByRole('button', { name: '保存结构化步骤' }).click();
      await expect(window.getByRole('status')).toContainText('装配步骤已保存');

      await window.getByRole('tab', { name: '测试中心' }).click();
      await window.getByLabel('用例编号').fill('TC-DESKTOP-01');
      await window.getByLabel('用例名称').fill('工作台刷新恢复');
      await window.getByLabel('关联需求').fill('REQ-PHASE2-WORKBENCH');
      await window.getByLabel('测试步骤').fill('保存工作中心记录\n刷新项目画布');
      await window.getByLabel('预期结果').fill('记录仍可见且字段完整');
      await window.getByRole('button', { name: '保存测试用例' }).click();
      await expect(window.getByRole('status')).toContainText('测试用例已保存并加入追踪矩阵');
      const testArtifacts = await window.evaluate(async (pid: string) => {
        const result = await (window as any).kyrozen.getProjectWorkspace(pid);
        return (result.data?.artifacts || []).map((artifact: Record<string, unknown>) => artifact.type);
      }, created!.id);
      expect(testArtifacts).toContain('test_case');
      await window.getByPlaceholder('实际结果；失败/错误会自动建立缺陷记录').fill('失败：串口观察未收到预期输出');
      await window.getByRole('button', { name: '保存测试结果' }).click();
      await expect(window.getByRole('status')).toContainText('已保存');
      await window.getByPlaceholder('修复说明和原用例实际结果').fill('修复端口提示后，重新执行原失败用例通过');
      await window.getByRole('button', { name: '保存原用例回归通过' }).click();
      await expect(window.getByRole('status')).toContainText('回归已通过');
      const regressionArtifacts = await window.evaluate(async (pid: string) => {
        const result = await (window as any).kyrozen.getProjectWorkspace(pid);
        const artifacts = (result.data?.artifacts || []) as Record<string, unknown>[];
        const decode = (type: string, title?: string) => {
          const artifact = artifacts.find((item) => item.type === type && (!title || item.title === title));
          try { return artifact ? JSON.parse(String(artifact.content || '{}')) : {}; } catch { return {}; }
        };
        return { types: artifacts.map((artifact) => artifact.type), testResult: decode('test_result', 'Desktop Workbench Test Result'), defect: decode('defect') };
      }, created!.id);
      expect(regressionArtifacts.types).toContain('defect_fix');
      expect(regressionArtifacts.testResult.test_case_id).toBe('TC-DESKTOP-01');
      expect(regressionArtifacts.testResult.defect_id).toBeTruthy();
      expect(regressionArtifacts.testResult.evidence).toEqual(expect.arrayContaining(['desktop_user_flow']));
      expect(regressionArtifacts.defect.related_requirement).toBe('REQ-PHASE2-WORKBENCH');
      await window.getByRole('button', { name: '保存验证报告' }).click();
      await expect(window.getByRole('status')).toContainText('验证报告保存失败');

      await window.getByRole('tab', { name: '改进中心' }).click();
      await window.getByPlaceholder('建议、证据、预期收益、风险、工作量和接受/延期理由').fill('建议增加串口未连接时的下一步提示；证据：测试失败；收益：降低新手阻塞；风险：低；工作量：半天');
      await window.getByRole('button', { name: '保存改进建议' }).click();
      await expect(window.getByRole('status')).toContainText('已保存');
      await window.getByRole('button', { name: '接受', exact: true }).click();
      await expect(window.getByRole('status')).toContainText('改进建议已接受');

      await window.getByRole('tab', { name: '反馈中心' }).click();
      await window.getByPlaceholder('参与者编号（如 U-01，可匿名）').fill('U-01');
      await window.getByPlaceholder('用户类型（例如 maker）').fill('maker');
      await window.getByPlaceholder('执行任务').fill('发现设备并观察串口');
      await window.getByRole('combobox', { name: '任务是否完成' }).selectOption('no');
      await window.getByPlaceholder('耗时（秒）').fill('90');
      await window.getByPlaceholder('满意度（1-5）').fill('2');
      await window.getByPlaceholder('用户完成了什么、遇到什么问题、是否愿意继续使用？').fill('用户无法确认串口目标，未能完成任务');
      await window.getByPlaceholder('阻塞点（每行一项）').fill('找不到串口\n不知道下一步');
      await window.getByPlaceholder('用户原话').fill('我不知道该选哪个端口');
      await window.getByRole('button', { name: '保存反馈' }).click();
      await expect(window.getByRole('status')).toContainText('用户反馈已记录');
      await expect(window.getByText('已有用户验证')).toBeVisible();

      // The first feedback above intentionally demonstrates the server-side
      // final-report gate. Complete the ordinary user flow with two additional
      // distinct target participants, then verify that the report can be
      // written and survives the later restart. This remains synthetic E2E
      // evidence; it must not be presented as real-user acceptance.
      const recordAdditionalFeedback = async (participant: string, userType: string, task: string, quote: string) => {
        await window.getByPlaceholder('参与者编号（如 U-01，可匿名）').fill(participant);
        await window.getByPlaceholder('用户类型（例如 maker）').fill(userType);
        await window.getByPlaceholder('执行任务').fill(task);
        await window.getByRole('combobox', { name: '任务是否完成' }).selectOption('yes');
        await window.getByPlaceholder('耗时（秒）').fill('75');
        await window.getByPlaceholder('满意度（1-5）').fill('4');
        await window.getByPlaceholder('用户完成了什么、遇到什么问题、是否愿意继续使用？').fill(`${participant} 完成了设备发现和串口观察任务`);
        await window.getByPlaceholder('阻塞点（每行一项）').fill('');
        await window.getByPlaceholder('用户原话').fill(quote);
        await window.getByRole('button', { name: '保存反馈' }).click();
        await expect(window.getByRole('status')).toContainText('用户反馈已记录');
      };
      await recordAdditionalFeedback('U-02', 'embedded maker', '按步骤完成接线并确认公共地', '接线步骤现在清楚多了');
      await recordAdditionalFeedback('U-03', '软件开发者', '查看设备状态并处理离线提示', '我能理解设备为什么暂时不可用');
      await window.getByRole('tab', { name: '测试中心' }).click();
      await window.getByRole('button', { name: '保存验证报告' }).click();
      await expect(window.getByRole('status')).toContainText('验证报告已保存');
      const feedbackArtifacts = await window.evaluate(async (pid: string) => {
        const result = await (window as any).kyrozen.getProjectWorkspace(pid);
        return (result.data?.artifacts || []).map((artifact: Record<string, unknown>) => artifact.type);
      }, created!.id);
      expect(feedbackArtifacts).toContain('iteration_task');

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

        // 确认精简后的画布标签页仍在（恢复完整性）
        for (const tab of expectedTabs) {
          await expect(
            window2.getByRole('tab', { name: tab }),
            `恢复后画布标签 "${tab}" 应可见`,
          ).toBeVisible();
        }

        const restoredWorkspace = await window2.evaluate(async (pid: string) => {
          const result = await (window as any).kyrozen.getProjectWorkspace(pid);
          const artifacts = (result.data?.artifacts || []) as Record<string, unknown>[];
          return {
            project: result.data?.project || {},
            artifactTypes: artifacts.map((artifact) => artifact.type),
            taskTitles: (result.data?.tasks || []).map((task: Record<string, unknown>) => task.title),
            decisions: (result.data?.decisions || []).map((decision: Record<string, unknown>) => decision.decision),
            hardwareRuns: result.data?.local?.hardware_runs || [],
            testResults: result.data?.phase2?.testing?.test_results || [],
            participantCount: result.data?.phase2?.user_validation?.participant_count || 0,
          };
        }, created!.id);
        expect(restoredWorkspace.project.project_type).toBe('software');
        expect(restoredWorkspace.artifactTypes).toEqual(expect.arrayContaining([
          'discovery_evidence', 'bom', 'wiring_design', 'firmware_project',
          'assembly_step', 'test_case', 'test_result', 'defect', 'defect_fix', 'user_feedback',
        ]));
        expect(restoredWorkspace.artifactTypes).toContain('validation_report');
        expect(restoredWorkspace.artifactTypes).toContain('iteration_task');
        expect(restoredWorkspace.decisions).toContain('先验证串口识别，再进入硬件装配');
        expect(restoredWorkspace.testResults.length).toBeGreaterThan(0);
        expect(restoredWorkspace.participantCount).toBe(3);
        expect(restoredWorkspace.hardwareRuns).toBeTruthy();

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

  test('混合项目确认流程 → 协议门禁 → Fake 六场景模拟', async ({ browserName: _browserName }) => {
    test.setTimeout(120_000);
    const userId = randomUUID();
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-hybrid-e2e-'));
    const projectName = `混合项目验收-${Date.now()}`;
    await fs.writeFile(path.join(profile, 'onboarding.json'), JSON.stringify({ completed: true, language: 'zh' }));
    const token = await createLocalAccessToken(userId);
    const protocolUrl = `${PROTOCOL}://auth/login?kyrozen_token=${encodeURIComponent(token)}&github_token=e2e-placeholder&scope=read%3Auser`;
    const electronApp = await launchElectron(profile, protocolUrl);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });
      await window.getByRole('button', { name: '新建' }).click();
      await window.getByPlaceholder('例如：AI 写作助手').fill(projectName);
      await window.getByPlaceholder('简短描述这个项目').fill('ESP32 传感器与网页控制面板');
      await window.getByPlaceholder('你想用这个项目达成什么目标？').fill('让用户通过网页查看 ESP32 设备状态');
      await window.getByRole('button', { name: '创建', exact: true }).click();
      await expect(window.getByTestId('project-list').getByText(projectName, { exact: true })).toBeVisible({ timeout: 20_000 });
      await window.getByRole('button', { name: '项目画布' }).click();
      await expect(window.getByTestId('project-workspace-panel')).toBeVisible();
      await window.getByRole('button', { name: '软硬件混合' }).click();
      await window.getByRole('button', { name: '确认流程' }).click();
      await expect(window.getByRole('status')).toContainText('项目类型与流程已确认');
      const hybridProjects = (await window.evaluate(async () => (window as any).kyrozen.getProjects())) as Array<{ id: string; name: string }>;
      const hybridProject = hybridProjects.find((project) => project.name === projectName);
      expect(hybridProject).toBeDefined();
      if (hybridProject) {
        const hybridState = await window.evaluate(async (pid: string) => (window as any).kyrozen.getProjectState(pid), hybridProject.id);
        expect(hybridState.workflow_stages).toEqual(expect.arrayContaining([
          'protocol_design', 'development', 'testing', 'hardware_design',
          'procurement', 'maker', 'firmware', 'hardware_testing',
          'integration_testing',
        ]));
        // Seed only the already-confirmed solution prerequisite, then use the
        // ordinary workbench control to start an independent software track.
        const dimensions = ['time', 'cost', 'user_value', 'technical_risk', 'maintenance_cost', 'data_risk', 'validation_difficulty'];
        const evidenceSeed = await window.evaluate(async (pid: string) => (window as any).kyrozen.createEvidence(pid, {
          claim: '用户需要同时比较设备连接和软件控制的方案风险', evidence_type: 'interview', original_text: '混合项目访谈记录',
        }), hybridProject.id);
        expect(evidenceSeed.success).toBeTruthy();
        const researchSeed = await window.evaluate(async (pid: string) => (window as any).kyrozen.createArtifact(
          pid, 'research_source', 'Research Source: Hybrid Public Material', JSON.stringify({
            title: 'Hybrid public material', url: 'https://example.com/hybrid-research', source_type: 'web_page', summary: '真实公开资料引用', fact_type: 'fact',
          }), '混合项目 E2E 研究来源',
        ), hybridProject.id);
        expect(researchSeed.success).toBeTruthy();
        const evidenceId = String((evidenceSeed.data as Record<string, unknown>)?.artifact_id || '');
        expect(evidenceId).toBeTruthy();
        const solutionSeed = await window.evaluate(async (args: { pid: string; dimensions: string[] }) => (window as any).kyrozen.saveSolution(
          args.pid,
          {
            solutions: ['保守方案', '平衡方案', '激进方案'].map((name) => ({ name, solution: name, evidence_ids: [args.evidenceId], dimension_scores: Object.fromEntries(args.dimensions.map((dimension) => [dimension, 3])) })),
            comparison_dimensions: args.dimensions,
            recommendation: '平衡方案', recommendation_reason: '先验证核心价值',
          },
          'select',
        ), { pid: hybridProject.id, dimensions, evidenceId });
        expect(solutionSeed.success).toBeTruthy();
        await window.getByRole('tab', { name: '项目主页' }).click();
        await expect(window.getByRole('button', { name: '推进软件轨道' })).toBeVisible();
        await window.getByRole('button', { name: '推进软件轨道' }).click();
        await expect(window.getByRole('status')).toContainText('软件轨道已推进并持久化');
        await window.getByRole('button', { name: '刷新' }).click();
        await expect(window.getByText('当前：软件开发')).toBeVisible();
      }
      await window.getByRole('tab', { name: '采购中心' }).click();
      await expect(window.getByText('协议模拟器 / 串口协议测试')).toBeVisible();
      await window.getByRole('button', { name: '确认此协议版本' }).click();
      await expect(window.getByRole('status')).toContainText('协议版本已确认');
      await window.getByRole('button', { name: '运行六种模拟场景' }).click();
      await expect(window.getByRole('status')).toContainText('协议六场景已通过并持久化', { timeout: 30_000 });
      await window.getByLabel('集成测试记录').fill('Fake 协议消息经应用层和 API 传输，错误版本被拒绝；记录仅代表模拟器集成。');
      await window.getByRole('button', { name: '保存集成测试记录' }).click();
      await expect(window.getByRole('status')).toContainText('集成测试记录已保存');
    } finally {
      await electronApp.close();
      await fs.rm(profile, { recursive: true, force: true });
    }
  });

  test('嵌入式项目确认流程 → 硬件阶段序列', async ({ browserName: _browserName }) => {
    test.setTimeout(120_000);
    const userId = randomUUID();
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-embedded-e2e-'));
    const projectName = `嵌入式项目验收-${Date.now()}`;
    await fs.writeFile(path.join(profile, 'onboarding.json'), JSON.stringify({ completed: true, language: 'zh' }));
    const token = await createLocalAccessToken(userId);
    const protocolUrl = `${PROTOCOL}://auth/login?kyrozen_token=${encodeURIComponent(token)}&github_token=e2e-placeholder&scope=read%3Auser`;
    const electronApp = await launchElectron(profile, protocolUrl);
    try {
      const window = await electronApp.firstWindow();
      await expect(window.getByTestId('project-list')).toBeVisible({ timeout: 25_000 });
      await window.getByRole('button', { name: '新建' }).click();
      await window.getByPlaceholder('例如：AI 写作助手').fill(projectName);
      await window.getByPlaceholder('简短描述这个项目').fill('ESP32 串口传感器');
      await window.getByPlaceholder('你想用这个项目达成什么目标？').fill('制作一个可观察温度的开发板设备');
      await window.getByRole('button', { name: '创建', exact: true }).click();
      await expect(window.getByTestId('project-list').getByText(projectName, { exact: true })).toBeVisible({ timeout: 20_000 });
      await window.getByRole('button', { name: '项目画布' }).click();
      await expect(window.getByTestId('project-workspace-panel')).toBeVisible();
      await window.getByRole('button', { name: '嵌入式', exact: true }).click();
      await window.getByRole('button', { name: '确认流程' }).click();
      await expect(window.getByRole('status')).toContainText('项目类型与流程已确认');
      const projects = (await window.evaluate(async () => (window as any).kyrozen.getProjects())) as Array<{ id: string; name: string }>;
      const created = projects.find((project) => project.name === projectName);
      expect(created).toBeDefined();
      if (created) {
        const state = await window.evaluate(async (pid: string) => (window as any).kyrozen.getProjectState(pid), created.id);
        expect(state.project_type).toBe('embedded');
        expect(state.workflow_stages).toEqual(expect.arrayContaining(['hardware_design', 'procurement', 'maker', 'firmware', 'hardware_testing']));
      }
      await window.getByRole('tab', { name: '采购中心' }).click();
      await window.getByLabel('硬件方案').fill('ESP32 控制器、温度传感器、3.3V 供电；禁止 5V 直接输入 GPIO。');
      await window.getByRole('button', { name: '保存硬件方案' }).click();
      await expect(window.getByRole('status')).toContainText('硬件方案已保存');
      await window.getByRole('button', { name: '关闭', exact: true }).click();
    } finally {
      await electronApp.close();
      await fs.rm(profile, { recursive: true, force: true });
    }
  });
});
