/**
 * Self-contained smoke test for the Kyrozen desktop client.
 *
 * Run with:
 *   npx tsx scripts/smoke-test.ts
 *
 * It will:
 *   1. Start the backend API server (if not already running).
 *   2. Build the renderer + Electron main process.
 *   3. Launch Electron via Playwright with an isolated profile.
 *   4. Automatically log in with the e2e test account.
 *   5. Wait for the project list to load.
 *   6. Take screenshots and print the main process log.
 *   7. Tear everything down.
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
    console.log('[smoke] Backend already running');
    return null;
  }
  console.log('[smoke] Starting backend...');
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
  console.log('[smoke] Backend started');
  return proc;
}

async function buildDesktop(): Promise<void> {
  console.log('[smoke] Building desktop...');
  await new Promise<void>((resolve, reject) => {
    const proc = spawn('npm', ['run', 'build:renderer'], {
      cwd: DESKTOP_ROOT,
      stdio: 'inherit',
      shell: true,
    });
    proc.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`build exited ${code}`))));
  });
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

async function runTest(): Promise<void> {
  let app: ElectronApplication | null = null;
  let backend: ChildProcess | null = null;
  const userDataDir = mkdtempSync(path.join(os.tmpdir(), 'kyrozen-smoke-'));

  try {
    backend = await startBackend();
    await buildDesktop();

    // Use the backend venv so the smoke test does not download a new Python runtime.
    const pythonPath = path.join(REPO_ROOT, '.venv/bin/python');

    console.log('[smoke] Launching Electron...');
    app = await electron.launch({
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

    const page: Page = await app.firstWindow();

    // Capture renderer-side diagnostics.
    page.on('console', (msg) => console.log(`[renderer:console:${msg.type()}]`, msg.text()));
    page.on('pageerror', (err) => console.error('[renderer:pageerror]', err));
    page.on('crash', () => console.error('[renderer:crash]'));

    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/01-initial.png') });

    const hasKyrozen = await page.evaluate(() => typeof (window as any).kyrozen !== 'undefined');
    console.log('[smoke] window.kyrozen exposed:', hasKyrozen);

    console.log('[smoke] Filling login form...');
    await page.fill('input[name="email"]', TEST_EMAIL);
    await page.fill('input[name="password"]', TEST_PASSWORD);
    await page.fill('input[name="serverUrl"]', SERVER_URL);
    await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/02-filled.png') });

    await page.click('button[type="submit"]');
    console.log('[smoke] Submitted login, waiting for connection...');

    // Wait for either project list or error message.
    const projectList = page.locator('[data-testid="project-list"]');
    const errorMessage = page.locator('text=/登录失败|连接错误|错误/i');
    await Promise.race([
      projectList.waitFor({ timeout: 30000 }).catch(() => {}),
      errorMessage.waitFor({ timeout: 30000 }).catch(() => {}),
    ]);

    await page.screenshot({ path: path.join(DESKTOP_ROOT, 'e2e/screenshots/03-after-login.png') });

    const hasProjectList = await projectList.isVisible().catch(() => false);
    const errorText = await errorMessage.textContent().catch(() => null);

    if (hasProjectList) {
      console.log('[smoke] ✅ Project list loaded');
    } else {
      console.log('[smoke] ❌ Project list NOT loaded');
      if (errorText) console.log('[smoke] Error text on page:', errorText);
    }

    console.log('\n[smoke] ----- Main process log -----');
    console.log(await tailLog(app));
    console.log('[smoke] ----- End of log -----\n');

    if (!hasProjectList) {
      throw new Error('Project list did not load after login');
    }
  } finally {
    if (app) {
      console.log('[smoke] Closing Electron...');
      await app.close();
    }
    if (backend) {
      console.log('[smoke] Stopping backend...');
      backend.kill('SIGTERM');
    }
    try {
      await rm(userDataDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  }
}

runTest().catch((err) => {
  console.error('[smoke] Unhandled error:', err);
  process.exit(1);
});
