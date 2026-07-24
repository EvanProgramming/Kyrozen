/**
 * Real-user journey test for the Kyrozen desktop client.
 *
 * This script walks through the MVP desktop features described in
 * DESKTOP_CLIENT_ARCHITECTURE.md without triggering any LLM calls,
 * so it does not consume Kyrozen model tokens.
 *
 * Covered flows:
 *   - Launch the desktop app.
 *   - Account/password login.
 *   - WebSocket connection and project list sync.
 *   - Project selection and chat UI activation.
 *   - Encrypted credential persistence and session resume on relaunch.
 */
import { spawn, ChildProcess } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { _electron as electron } from 'playwright';
import type { ElectronApplication, Page } from 'playwright';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..', '..');
const DESKTOP_ROOT = path.resolve(SCRIPT_DIR, '..');

const TEST_EMAIL = 'test_kyrozen_e2e_20260724@example.com';
const TEST_PASSWORD = 'KyrozenTest2026!';
const SERVER_URL = 'http://127.0.0.1:8000';

interface ProjectSummary {
  id: string;
  name: string;
  current_stage: string;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForServer(timeout = 30000): Promise<boolean> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${SERVER_URL}/api/health`);
      if (res.ok) return true;
    } catch {
      // not ready yet
    }
    await sleep(500);
  }
  return false;
}

async function startBackend(): Promise<ChildProcess | null> {
  if (await waitForServer(2000)) {
    console.log('[journey] Backend already running');
    return null;
  }
  console.log('[journey] Starting backend...');
  const proc = spawn(
    path.join(REPO_ROOT, '.venv/bin/python'),
    ['-m', 'uvicorn', 'kyrozen.api.server:app', '--host', '127.0.0.1', '--port', '8000'],
    { cwd: REPO_ROOT, stdio: 'pipe' }
  );
  proc.stdout?.on('data', (d) => console.log('[backend]', d.toString().trimEnd()));
  proc.stderr?.on('data', (d) => console.error('[backend]', d.toString().trimEnd()));
  if (!(await waitForServer(30000))) {
    throw new Error('Backend failed to start');
  }
  console.log('[journey] Backend started');
  return proc;
}

async function buildDesktop(): Promise<void> {
  console.log('[journey] Building desktop...');
  await new Promise<void>((resolve, reject) => {
    const proc = spawn('npm', ['run', 'build:renderer'], {
      cwd: DESKTOP_ROOT,
      stdio: 'inherit',
      shell: true,
    });
    proc.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`build exited ${code}`))));
  });
}

async function ensureTestProject(): Promise<ProjectSummary> {
  const signin = await fetch(`${SERVER_URL}/api/auth/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
  });
  if (!signin.ok) {
    throw new Error(`Failed to sign in test account: ${await signin.text()}`);
  }
  const { access_token: accessToken } = (await signin.json()) as { access_token: string };

  const listRes = await fetch(`${SERVER_URL}/api/projects`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!listRes.ok) {
    throw new Error(`Failed to list projects: ${await listRes.text()}`);
  }
  const projects = (await listRes.json()) as ProjectSummary[];
  if (projects.length > 0) {
    console.log('[journey] Using existing test project:', projects[0].name);
    return projects[0];
  }

  const createRes = await fetch(`${SERVER_URL}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({
      name: 'Desktop Journey Test Project',
      description: 'Created automatically for desktop client user journey testing.',
      goal: 'Validate desktop client MVP flows.',
      initial_idea: 'Desktop client smoke test',
    }),
  });
  if (!createRes.ok) {
    throw new Error(`Failed to create test project: ${await createRes.text()}`);
  }
  const project = (await createRes.json()) as ProjectSummary;
  console.log('[journey] Created test project:', project.name);
  return project;
}

async function getMainLogPath(app: ElectronApplication): Promise<string> {
  const userData = await app.evaluate(({ app: electronApp }) => electronApp.getPath('userData'));
  return path.join(String(userData), 'logs', 'main.log');
}

async function tailLog(app: ElectronApplication): Promise<string> {
  try {
    const logPath = await getMainLogPath(app);
    return await readFile(logPath, 'utf-8');
  } catch {
    return '(log file not found)';
  }
}

function attachDiagnostics(page: Page) {
  page.on('console', (msg) => console.log(`[renderer:console:${msg.type()}]`, msg.text()));
  page.on('pageerror', (err) => console.error('[renderer:pageerror]', err));
  page.on('crash', () => console.error('[renderer:crash]'));
}

async function launchApp(userDataDir: string): Promise<ElectronApplication> {
  const pythonPath = path.join(REPO_ROOT, '.venv/bin/python');
  return electron.launch({
    args: [
      path.join(DESKTOP_ROOT, 'dist-electron/main/main.js'),
      `--user-data-dir=${userDataDir}`,
    ],
    env: {
      ...process.env,
      NODE_ENV: 'production',
      KYROZEN_DESKTOP_SERVER_URL: SERVER_URL,
      KYROZEN_PYTHON_PATH: pythonPath,
    },
  });
}

async function runLoginFlow(page: Page): Promise<void> {
  await page.waitForSelector('input[name="email"]', { timeout: 30000 });
  await page.fill('input[name="email"]', TEST_EMAIL);
  await page.fill('input[name="password"]', TEST_PASSWORD);
  await page.fill('input[name="serverUrl"]', SERVER_URL);
  await page.click('button[type="submit"]');
}

async function waitForProjectList(page: Page): Promise<void> {
  await page.waitForSelector('[data-testid="project-list"]', { timeout: 30000 });
  // Give the WebSocket handshake a moment to settle.
  await page.waitForTimeout(500);
}

async function assertConnectionConnected(page: Page): Promise<boolean> {
  try {
    // The ConnectionStatus component uses bg-green-600 when state === 'connected'.
    await page.waitForSelector('.bg-green-600', { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

async function runJourney(): Promise<void> {
  let app: ElectronApplication | null = null;
  let backend: ChildProcess | null = null;
  const userDataDir = mkdtempSync(path.join(os.tmpdir(), 'kyrozen-journey-'));
  const results: Record<string, string> = {};

  try {
    backend = await startBackend();
    await buildDesktop();
    const testProject = await ensureTestProject();

    // ---------- First launch: manual login ----------
    console.log('[journey] First launch: manual login');
    app = await launchApp(userDataDir);
    const page = await app.firstWindow();
    attachDiagnostics(page);

    await page.waitForLoadState('domcontentloaded');
    await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/journey-01-login.png') });

    await runLoginFlow(page);
    await waitForProjectList(page);
    await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/journey-02-logged-in.png') });

    results['manual-login'] = 'pass';
    results['project-list-sync'] = 'pass';

    const connected = await assertConnectionConnected(page);
    results['websocket-connected'] = connected ? 'pass' : 'fail';
    console.log(`[journey] WebSocket connected: ${connected}`);

    // Select the test project.
    const projectButton = page.locator('aside button').first();
    const hasProjectButton = (await projectButton.count()) > 0;
    if (hasProjectButton) {
      await projectButton.click();
      await page.waitForTimeout(500);
      await page.waitForSelector(`text=当前项目：${testProject.name}`, { timeout: 10000 });
      await page.waitForSelector('input[placeholder="输入消息..."]', { timeout: 10000 });
      await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/journey-03-project-selected.png') });
      results['project-switch'] = 'pass';
      results['chat-input-active'] = 'pass';
    } else {
      results['project-switch'] = 'skipped (no project button)';
      results['chat-input-active'] = 'skipped';
    }

    console.log('\n[journey] ----- Main process log (first launch) -----');
    console.log(await tailLog(app));
    console.log('[journey] ----- End of log -----\n');

    await app.close();
    app = null;

    // ---------- Second launch: session resume ----------
    console.log('[journey] Second launch: session resume from encrypted credentials');
    app = await launchApp(userDataDir);
    const resumedPage = await app.firstWindow();
    attachDiagnostics(resumedPage);

    await resumedPage.waitForLoadState('domcontentloaded');
    await waitForProjectList(resumedPage);
    await resumedPage.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/journey-04-auto-login.png') });

    const stillOnLogin = (await resumedPage.locator('input[name="email"]').count()) > 0;
    results['credential-persistence'] = stillOnLogin ? 'fail (login form still visible)' : 'pass';
    console.log(`[journey] Auto-login after relaunch: ${stillOnLogin ? 'fail' : 'pass'}`);

    const resumedConnected = await assertConnectionConnected(resumedPage);
    results['websocket-reconnect'] = resumedConnected ? 'pass' : 'fail';
    console.log(`[journey] WebSocket reconnected: ${resumedConnected}`);

    console.log('\n[journey] ----- Main process log (second launch) -----');
    console.log(await tailLog(app));
    console.log('[journey] ----- End of log -----\n');

    // ---------- Report ----------
    console.log('[journey] ========== Test result summary ==========');
    for (const [item, result] of Object.entries(results)) {
      const icon = result.startsWith('pass') ? '✅' : result.startsWith('fail') ? '❌' : '⏭️';
      console.log(`${icon} ${item}: ${result}`);
    }
    console.log('[journey] ===========================================');

    const failed = Object.values(results).some((r) => r.startsWith('fail'));
    if (failed) {
      throw new Error('Some user-journey checks failed');
    }
  } finally {
    if (app) {
      console.log('[journey] Closing Electron...');
      await app.close();
    }
    if (backend) {
      console.log('[journey] Stopping backend...');
      backend.kill('SIGTERM');
    }
    try {
      await rm(userDataDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  }
}

runJourney().catch((err) => {
  console.error('[journey] Unhandled error:', err);
  process.exit(1);
});
