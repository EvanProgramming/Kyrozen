import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, safeStorage, shell, Tray } from 'electron';
import path from 'path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs/promises';
import http from 'http';
import { watch, FSWatcher } from 'fs';
import WebSocket from 'ws';
import {
  getWebSocketUrlFromHttp,
  normalizeServerUrl,
  resolveDefaultServerUrl,
} from './serverUrl';
import {
  checkAndUpdateHardwareToolchain,
  ensureArduinoCLI,
  ensurePlatformIO,
  getToolStatus,
  installCommonCores,
  resolveHardwareCommand,
  setPythonExe,
  startHardwareToolchainAutoUpdate,
  stopHardwareToolchainAutoUpdate,
} from './hardwareToolchain';
import { startExtensionServer, ClipPayload, TestReportPayload } from './extensionServer';
import { registerNativeMessagingHost } from './nativeMessagingRegistry';
import { ensurePythonRuntime, getCachedPythonRuntime } from './pythonRuntime';
import {
  ensureProjectVenv,
  getProjectVenv,
  installProjectDependencies,
} from './pythonVenv';
import {
  checkForUpdates,
  initAutoUpdater,
  setUpdateApiBaseUrl,
  stopUpdateChecks,
} from './updater';
import {
  commitAndPush,
  getAutoCommit,
  getGitCommits,
  getGitStatus,
  initGitRepo,
  maybeAutoCommit,
  setAutoCommit,
  classifyCreateRepoError,
} from './gitOperations';

interface WorkspaceMap {
  [projectId: string]: string;
}

const isDev = process.env.NODE_ENV === 'development';
const currentDir = path.dirname(fileURLToPath(import.meta.url));

const LOG_DIR = path.join(app.getPath('userData'), 'logs');
const LOG_FILE = path.join(LOG_DIR, 'main.log');

async function writeLog(level: string, message: string): Promise<void> {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [${level}] ${message}\n`;
  try {
    await fs.mkdir(LOG_DIR, { recursive: true });
    await fs.appendFile(LOG_FILE, line, 'utf-8');
  } catch (err) {
    // Fallback to console if logging fails.
    console.error('[Kyrozen] Failed to write log:', err);
  }
  // Also mirror to console in dev mode.
  if (isDev) {
    console.log(line.trimEnd());
  }
}

const logInfo = (msg: string) => writeLog('INFO', msg);
const logError = (msg: string) => writeLog('ERROR', msg);
const logWarn = (msg: string) => writeLog('WARN', msg);

function redactProtocolUrl(url: string): string {
  try {
    const parsed = new URL(url);
    for (const key of ['token', 'kyrozen_token', 'refresh_token', 'github_token', 'access_token']) {
      if (parsed.searchParams.has(key)) parsed.searchParams.set(key, '<REDACTED>');
    }
    return parsed.toString();
  } catch {
    return '<invalid protocol URL>';
  }
}

let mainWindow: BrowserWindow | null = null;
let wsClient: WebSocket | null = null;
let pythonAgent: ChildProcessWithoutNullStreams | null = null;
let pythonAgentStartPromise: Promise<void> | null = null;
let pythonAgentStdoutBuffer = '';
let pythonAgentReady = false;
let currentProjectId: string | null = null;
// Default server URL. resolveDefaultServerUrl() seeds this from the
// KYROZEN_DESKTOP_SERVER_URL env var (so a packaged build can target a server
// by IP) and falls back to localhost. A persisted server URL (from a previous
// login) overrides this at startup via loadCredentials().
let serverUrl = resolveDefaultServerUrl();
let wsUrl = getWebSocketUrlFromHttp(serverUrl);
let reconnectTimer: NodeJS.Timeout | null = null;
let heartbeatTimer: NodeJS.Timeout | null = null;
let workspaceMap: WorkspaceMap = {};
let workspaceNames: Record<string, string> = {};
let currentTaskId: string | null = null;
let currentTaskRunning = false;
// Tasks the user cancelled: any late `completed` result for these ids must
// never be appended to the chat (cancel race fix, acceptance 2026-07-30).
const cancelledTaskIds = new Set<string>();
// Dispatch watchdog: after /api/chat reports dispatched_to_desktop, the
// matching assign_task must arrive over WS within this window; otherwise the
// renderer would stay stuck on "正在理解你的需求" forever.
let dispatchWatchdogTimer: NodeJS.Timeout | null = null;
let dispatchWatchdogTaskId: string | null = null;
const DISPATCH_WATCHDOG_MS = 30_000;

function startDispatchWatchdog(taskId: string) {
  clearDispatchWatchdog();
  dispatchWatchdogTaskId = taskId;
  dispatchWatchdogTimer = setTimeout(() => {
    dispatchWatchdogTimer = null;
    if (dispatchWatchdogTaskId !== taskId || currentTaskRunning) return;
    logWarn(`Dispatched task ${taskId} never arrived over WebSocket`);
    sendTaskActivity({ task_id: taskId, description: '任务派发失败', status: 'failed' });
    sendChatMessage({
      role: 'error',
      content: '',
      error: '任务派发超时：云端未能把任务送达本地 Agent，请检查网络后重新发送。',
      operations: [],
    });
  }, DISPATCH_WATCHDOG_MS);
}

function clearDispatchWatchdog(taskId?: string) {
  if (taskId && dispatchWatchdogTaskId && taskId !== dispatchWatchdogTaskId) return;
  if (dispatchWatchdogTimer) {
    clearTimeout(dispatchWatchdogTimer);
    dispatchWatchdogTimer = null;
  }
  dispatchWatchdogTaskId = null;
}
let previewWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonAgentRestartCount = 0;
const PYTHON_AGENT_MAX_RESTARTS = 5;
let pythonAgentStopping = false;
let isQuitting = false;
let fullTrustMode = false;
let githubAccessToken: string | null = null;
let githubTokenScope: string | null = null;
const taskOperations = new Map<string, Array<{ description: string; status: string; timestamp: string }>>();
const pendingConfirmations = new Map<string, Record<string, unknown>>();
const trustedOperationTypes = new Set<string>();

// Ensure only one instance of the desktop client is running. On Windows/Linux,
// opening a kyrozen:// URL while the app is already running will be forwarded
// to the existing instance via the second-instance event.
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

app.on('second-instance', (_event, argv) => {
  const url = argv.find((arg) => arg.startsWith(`${PROTOCOL_SCHEME}://`));
  if (url && mainWindow) {
    logInfo(`Received protocol URL from second instance: ${redactProtocolUrl(url)}`);
    if (mainWindow.webContents.isLoading()) {
      mainWindow.webContents.once('did-finish-load', () => {
        void handleProtocolUrl(url);
      });
    } else {
      void handleProtocolUrl(url);
    }
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
let pendingCloudMessages: string[] = [];
let accessToken: string | null = null;
let currentWsToken: string | null = null;
let projectFileWatchers = new Map<string, FSWatcher>();
let pendingFileChanges = new Map<string, NodeJS.Timeout>();
let pendingAutoCommit = new Map<string, NodeJS.Timeout>();
let pendingTasks: Array<Record<string, unknown>> = [];
let pythonRuntimePath: string | null = null;
let pythonRuntimeReady = false;
let extensionServer: http.Server | null = null;
let taskTimeoutTimer: NodeJS.Timeout | null = null;
let lastTaskPayload: Record<string, unknown> | null = null;
let taskRetryCount = 0;
const MAX_TASK_RETRIES = 2;
let sessionRefreshTimer: NodeJS.Timeout | null = null;
let refreshTokenInvalid = false;

const PROTOCOL_SCHEME = 'kyrozen';
const HEARTBEAT_INTERVAL_MS = 30_000;
const TASK_TIMEOUT_MS = 10 * 60 * 1000;
const DEPENDENCY_TIMEOUT_MS = 5 * 60 * 1000;
const MODEL_TIMEOUT_MS = 2 * 60 * 1000;
const HARDWARE_TIMEOUT_MS = 15 * 60 * 1000;
const SESSION_REFRESH_FALLBACK_MS = 5 * 60 * 1000;
const SESSION_REFRESH_LEEWAY_MS = 2 * 60 * 1000;

const WORKSPACE_CONFIG_PATH = path.join(app.getPath('userData'), 'workspaces.json');
const WORKSPACE_NAMES_PATH = path.join(app.getPath('userData'), 'workspace-names.json');
const TOKEN_STORE_PATH = path.join(app.getPath('userData'), 'credentials.json');
const ONBOARDING_CONFIG_PATH = path.join(app.getPath('userData'), 'onboarding.json');

interface OnboardingConfig {
  completed: boolean;
  language: 'zh' | 'en';
  completedAt?: string;
}

function shouldUseSafeStorage(): boolean {
  if (process.env.KYROZEN_DISABLE_KEYCHAIN === '1') return false;
  // The public beta is intentionally ad-hoc signed. On macOS, repeated ad-hoc
  // package replacement can make safeStorage/Keychain access block for over a
  // minute. Use a chmod-0600 file for that distribution; an official
  // Developer-ID build opts back into Keychain with KYROZEN_SIGNED_BUILD=1.
  if (app.isPackaged && process.env.KYROZEN_SIGNED_BUILD !== '1') return false;
  return safeStorage.isEncryptionAvailable();
}

let onboardingConfig: OnboardingConfig = { completed: false, language: 'zh' };

async function loadOnboardingConfig(): Promise<OnboardingConfig> {
  try {
    const raw = await fs.readFile(ONBOARDING_CONFIG_PATH, 'utf-8');
    const parsed = JSON.parse(raw) as Partial<OnboardingConfig>;
    return {
      completed: parsed.completed ?? false,
      language: parsed.language ?? 'zh',
      completedAt: parsed.completedAt,
    };
  } catch {
    return { completed: false, language: 'zh' };
  }
}

async function saveOnboardingConfig(patch: Partial<OnboardingConfig>): Promise<void> {
  onboardingConfig = { ...onboardingConfig, ...patch };
  await fs.mkdir(path.dirname(ONBOARDING_CONFIG_PATH), { recursive: true });
  await fs.writeFile(ONBOARDING_CONFIG_PATH, JSON.stringify(onboardingConfig, null, 2));
}

async function loadWorkspaceMap(): Promise<void> {
  try {
    const raw = await fs.readFile(WORKSPACE_CONFIG_PATH, 'utf-8');
    workspaceMap = JSON.parse(raw);
  } catch {
    workspaceMap = {};
  }
}

async function saveWorkspaceMap(): Promise<void> {
  await fs.mkdir(path.dirname(WORKSPACE_CONFIG_PATH), { recursive: true });
  await fs.writeFile(WORKSPACE_CONFIG_PATH, JSON.stringify(workspaceMap, null, 2));
}

async function loadWorkspaceNames(): Promise<void> {
  try {
    const raw = await fs.readFile(WORKSPACE_NAMES_PATH, 'utf-8');
    const parsed = JSON.parse(raw);
    workspaceNames = parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    workspaceNames = {};
  }
}

async function saveWorkspaceNames(): Promise<void> {
  await fs.mkdir(path.dirname(WORKSPACE_NAMES_PATH), { recursive: true });
  await fs.writeFile(WORKSPACE_NAMES_PATH, JSON.stringify(workspaceNames, null, 2));
}

async function saveCredentials(
  wsToken: string,
  refreshToken?: string,
  accessToken?: string,
): Promise<void> {
  currentWsToken = wsToken;
  const payload = JSON.stringify({
    wsToken,
    refreshToken: refreshToken || null,
    accessToken: accessToken || null,
    serverUrl,
  });
  // P0-17: 默认使用 macOS Keychain 加密凭据。仅在 Electron safeStorage
  // 不可用时才回退明文（文件权限仍设为 0600）。
  // KYROZEN_DISABLE_KEYCHAIN=1 可强制回退明文（调试/CI 场景）。
  const useSafeStorage = shouldUseSafeStorage();
  const encrypted = useSafeStorage
    ? safeStorage.encryptString(payload)
    : Buffer.from(payload);
  await fs.mkdir(path.dirname(TOKEN_STORE_PATH), { recursive: true });
  await fs.writeFile(TOKEN_STORE_PATH, encrypted);
  await fs.chmod(TOKEN_STORE_PATH, 0o600).catch(() => undefined);
}

async function loadCredentials(): Promise<{
  wsToken: string;
  refreshToken: string | null;
  accessToken: string | null;
  serverUrl: string;
} | null> {
  try {
    logInfo(`Loading credentials from ${TOKEN_STORE_PATH}`);
    const raw = await fs.readFile(TOKEN_STORE_PATH);
    const useSafeStorage = shouldUseSafeStorage();
    // 兼容旧明文凭据：先尝试 Keychain 解密，失败则回退明文 JSON 解析。
    // 迁移到 Keychain 后下次 saveCredentials 会自动加密存储。
    let decrypted: string;
    if (useSafeStorage) {
      try {
        decrypted = safeStorage.decryptString(raw);
      } catch {
        decrypted = raw.toString();
      }
    } else {
      decrypted = raw.toString();
      // One-time migration from an older encrypted beta build. This may be
      // slow once, but saveCredentials rewrites the value in the unsigned
      // distribution's stable chmod-0600 format immediately afterwards.
      if (!decrypted.trimStart().startsWith('{') && safeStorage.isEncryptionAvailable()) {
        decrypted = safeStorage.decryptString(raw);
      }
    }
    const data = JSON.parse(decrypted);
    if (data.wsToken) {
      logInfo('Loaded existing credentials, resuming session');
      return {
        wsToken: data.wsToken,
        refreshToken: data.refreshToken || null,
        accessToken: data.accessToken || null,
        serverUrl: data.serverUrl || resolveDefaultServerUrl(),
      };
    }
  } catch (err: any) {
    logInfo(`No credentials found or failed to load: ${err.message || err}`);
  }
  return null;
}

async function clearCredentials(): Promise<void> {
  clearSessionRefreshTimer();
  refreshTokenInvalid = false;
  currentWsToken = null;
  accessToken = null;
  try {
    await fs.unlink(TOKEN_STORE_PATH);
  } catch {
    // ignore
  }
}

function clearSessionRefreshTimer(): void {
  if (sessionRefreshTimer) {
    clearTimeout(sessionRefreshTimer);
    sessionRefreshTimer = null;
  }
}

function accessTokenExpiryMs(token: string | null): number | null {
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as { exp?: number };
    return typeof decoded.exp === 'number' ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

function scheduleSessionRefresh(): void {
  clearSessionRefreshTimer();
  if (!accessToken) return;
  const expiry = accessTokenExpiryMs(accessToken);
  const delay = expiry
    ? Math.max(30_000, expiry - Date.now() - SESSION_REFRESH_LEEWAY_MS)
    : SESSION_REFRESH_FALLBACK_MS;
  sessionRefreshTimer = setTimeout(async () => {
    sessionRefreshTimer = null;
    if (await refreshAccessToken()) {
      scheduleSessionRefresh();
      // Access-token refresh does not renew the WebSocket token. Renew it before
      // its 24-hour TTL expires so an idle desktop remains signed in.
      await reconnectWithFreshWebSocketToken();
    } else if (!refreshTokenInvalid) {
      // A temporary outage must not turn into a logout. Retry with backoff.
      sessionRefreshTimer = setTimeout(scheduleSessionRefresh, SESSION_REFRESH_FALLBACK_MS);
    }
  }, delay);
}

async function saveServerUrl(url: string): Promise<void> {
  const normalized = normalizeServerUrl(url);
  serverUrl = normalized;
  setUpdateApiBaseUrl(serverUrl);
  wsUrl = getWebSocketUrlFromHttp(serverUrl);
  const credentials = await loadCredentials();
  if (credentials) {
    await saveCredentials(
      credentials.wsToken,
      credentials.refreshToken || undefined,
      credentials.accessToken || undefined,
    );
  }
}

function showNotification(title: string, body: string) {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show();
  }
}

// Server URL normalization and WebSocket-URL derivation now live in
// ./serverUrl.ts (imported at the top of this file) so they can be unit-tested
// and shared. They intentionally do NOT force TLS for non-localhost hosts,
// which lets the client reach a server directly by IP over plain HTTP when no
// domain / TLS certificate is available.

async function pickWorkspaceRoot(projectId: string): Promise<string | null> {
  const defaultPath = path.join(app.getPath('home'), 'KyrozenProjects', projectId);
  const result = await dialog.showOpenDialog(mainWindow!, {
    title: `选择项目 ${projectId} 的本地工作目录`,
    defaultPath,
    properties: ['openDirectory', 'createDirectory', 'promptToCreate'],
    buttonLabel: '选择此文件夹',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  const selected = result.filePaths[0];
  await fs.mkdir(selected, { recursive: true });
  workspaceMap[projectId] = selected;
  await saveWorkspaceMap();
  return selected;
}

async function getWorkspaceRoot(projectId: string | null): Promise<string | null> {
  if (!projectId) return null;
  if (workspaceMap[projectId]) {
    await fs.mkdir(workspaceMap[projectId], { recursive: true });
    return workspaceMap[projectId];
  }
  const defaultPath = path.join(app.getPath('home'), 'KyrozenProjects', projectId);
  await fs.mkdir(defaultPath, { recursive: true });
  workspaceMap[projectId] = defaultPath;
  await saveWorkspaceMap();
  return defaultPath;
}

let currentConnectionState: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
let currentConnectionMessage = '未连接';

function updateConnection(state: 'disconnected' | 'connecting' | 'connected' | 'error', message: string) {
  currentConnectionState = state;
  currentConnectionMessage = message;
  logInfo(`Connection state: ${state} - ${message}`);
  mainWindow?.webContents.send('kyrozen:connection-change', state, message);
}

interface ChatMessage {
  role: string;
  content: string;
  raw?: string;
  error?: string;
  operations?: Array<{ description: string; status: string; timestamp: string }>;
}

function sendChatMessage(message: ChatMessage) {
  mainWindow?.webContents.send('kyrozen:chat-message', message);
}

function sendExecutionPlan(plan: { task_id: string; steps: string[] }) {
  mainWindow?.webContents.send('kyrozen:execution-plan', plan);
}

function sendTaskActivity(activity: { task_id?: string; description: string; status?: string }) {
  mainWindow?.webContents.send('kyrozen:task-activity', {
    task_id: activity.task_id || '',
    description: activity.description,
    status: activity.status || 'running',
  });
}

function decodeAccessTokenClaims(): Record<string, any> {
  if (!accessToken) return {};
  try {
    const payload = accessToken.split('.')[1];
    if (!payload) return {};
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));
  } catch {
    return {};
  }
}

function sendOnboardingProgress(step: string, message: string, payload?: Record<string, unknown>) {
  mainWindow?.webContents.send('kyrozen:onboarding-progress', { step, message, ...payload });
}

function createWindow() {
  logInfo('Creating main window');
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(currentDir, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    const devPort = process.env.VITE_DESKTOP_PORT || '5173';
    const devUrl = `http://localhost:${devPort}`;
    logInfo(`Loading dev URL: ${devUrl}`);
    mainWindow.loadURL(devUrl);
    // If the configured/default port is unavailable, fall back to other common Vite ports.
    mainWindow.webContents.on('did-fail-load', () => {
      if (!mainWindow) return;
      const fallbackPorts = ['5173', '5174', '5175', '5176', '5177', '5178'];
      const currentPort = new URL(mainWindow.webContents.getURL()).port || devPort;
      const remaining = fallbackPorts.filter((p) => p !== currentPort);
      if (remaining.length === 0) return;
      const nextPort = remaining[0];
      logWarn(`Dev server not found on ${currentPort}, trying ${nextPort}`);
      mainWindow.loadURL(`http://localhost:${nextPort}`);
    });
  } else {
    const prodUrl = path.join(currentDir, '../../dist/index.html');
    logInfo(`Loading production file: ${prodUrl}`);
    mainWindow.loadFile(prodUrl);
  }

  // Close-to-tray behavior: clicking the window close button hides the window
  // so the WebSocket connection and Python Agent keep running in the background.
  // A real quit must come from the tray menu or Cmd+Q / Alt+F4.
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  initAutoUpdater(mainWindow);

  mainWindow.on('close', (event) => {
    if (process.platform === 'darwin') return;
    event.preventDefault();
    mainWindow?.hide();
  });
}

function createTray() {
  const iconPath = path.join(currentDir, '../../public/tray-icon.png');
  let trayIcon: Electron.NativeImage | undefined;
  try {
    if (process.platform === 'darwin') {
      // On macOS, use a 16x16 template image if available; otherwise fall back to text title.
      const loaded = nativeImage.createFromPath(iconPath);
      trayIcon = loaded.resize({ width: 16, height: 16 });
    } else {
      trayIcon = nativeImage.createFromPath(iconPath);
    }
  } catch {
    trayIcon = undefined;
  }

  tray = new Tray(trayIcon || nativeImage.createEmpty());
  if (!trayIcon && process.platform === 'darwin') {
    tray.setTitle('K');
  }
  tray.setToolTip('Kyrozen Desktop');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else {
          createWindow();
        }
      },
    },
    {
      label: '设置',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
          mainWindow.webContents.send('kyrozen:open-settings');
        } else {
          createWindow();
        }
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
    { type: 'separator' },
    {
      label: '退出并清除登录状态',
      click: async () => {
        await clearCredentials();
        disconnectWebSocket();
        stopPythonAgent();
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    } else {
      createWindow();
    }
  });
}

function getProtocolUrl() {
  const args = process.argv.slice(1);
  return args.find((arg) => arg.startsWith(`${PROTOCOL_SCHEME}://`)) || null;
}

async function handleProtocolUrl(url: string) {
  logInfo(`Handling protocol URL: ${redactProtocolUrl(url)}`);
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'open') {
      const token = parsed.searchParams.get('token');
      if (token && mainWindow) {
        mainWindow.webContents.once('did-finish-load', () => {
          mainWindow?.webContents.send('kyrozen:protocol-url', url);
        });
      }
    } else if (parsed.hostname === 'auth' && parsed.pathname === '/login') {
      // GitHub OAuth login callback: kyrozen://auth/login?kyrozen_token=...&github_token=...
      const kyrozenToken = parsed.searchParams.get('kyrozen_token');
      const refreshTok = parsed.searchParams.get('refresh_token');
      const ghToken = parsed.searchParams.get('github_token');
      const scope = parsed.searchParams.get('scope') || '';
      if (kyrozenToken && ghToken) {
        accessToken = kyrozenToken;
        githubAccessToken = ghToken;
        githubTokenScope = scope;
        void storeGitHubToken(ghToken, scope);
        sendGitHubStatus();
        setUpdateApiBaseUrl(serverUrl);
        wsUrl = getWebSocketUrlFromHttp(serverUrl);
        // Exchange the Kyrozen JWT for a WS token and connect.
        try {
          const verify = await apiPost('/api/desktop/verify-token', {
            access_token: kyrozenToken,
            device_name: os.hostname(),
          });
          if (verify.ws_token) {
            // Keep the server-verifiable JWT. The generated desktop API token
            // is process-local and cannot restore a session after an API restart.
            accessToken = kyrozenToken;
            await saveCredentials(
              verify.ws_token,
              refreshTok || undefined,
              accessToken || undefined,
            );
            refreshTokenInvalid = false;
            scheduleSessionRefresh();
            connectWebSocket(verify.ws_token);
            mainWindow?.webContents.send('kyrozen:session-resumed', verify.ws_token, serverUrl);
            logInfo('GitHub login completed successfully');
          }
        } catch (err: any) {
          logError(`GitHub login verify-token failed: ${err.message || err}`);
        }
      }
    } else if (parsed.hostname === 'auth' && parsed.pathname === '/github') {
      const token = parsed.searchParams.get('token');
      const scope = parsed.searchParams.get('scope') || '';
      if (token) {
        githubAccessToken = token;
        githubTokenScope = scope;
        void storeGitHubToken(token, scope);
        sendGitHubStatus();
        sendTaskActivity({ description: 'GitHub 授权成功', status: 'completed' });
      }
    }
  } catch (err: any) {
    logError(`Failed to handle protocol URL: ${err.message || err}`);
  }
}

function sendGitHubStatus() {
  mainWindow?.webContents.send('kyrozen:github-status', {
    connected: !!githubAccessToken,
    scope: githubTokenScope,
  });
}

async function fetchGitHubToken(): Promise<void> {
  if (!accessToken) return;
  try {
    const data = await apiGet('/api/user/github-token');
    if (data.token) {
      githubAccessToken = data.token;
      githubTokenScope = data.scope || null;
      sendGitHubStatus();
      logInfo('Restored GitHub token from Supabase metadata');
    }
  } catch (err: any) {
    logInfo(`No GitHub token available: ${err.message || err}`);
  }
}

async function storeGitHubToken(token: string, scope: string): Promise<void> {
  if (!accessToken || !token) return;
  try {
    await apiPost('/api/user/github-token', { token, scope }, true);
    logInfo('Stored GitHub token to Supabase metadata');
  } catch (err: any) {
    logWarn(`Failed to store GitHub token: ${err.message || err}`);
  }
}

app.setAsDefaultProtocolClient(PROTOCOL_SCHEME);

app.whenReady().then(async () => {
  logInfo('App ready, initializing Kyrozen desktop client');
  await loadWorkspaceMap();
  await loadWorkspaceNames();
  onboardingConfig = await loadOnboardingConfig();
  createWindow();
  createTray();

  try {
    const ext = await startExtensionServer({
      onClip: (payload: ClipPayload) => {
        const summary = [payload.title, payload.url, payload.selection, payload.bodyText]
          .filter(Boolean)
          .join('\n\n');
        sendChatMessage({ role: 'user', content: `从浏览器扩展抓取的网页内容：\n\n${summary}` });
      },
      onTestReport: (payload: TestReportPayload) => {
        const errorText = payload.errors.length
          ? payload.errors.map((e) => `- ${e.message}${e.source ? ` (${e.source}:${e.line})` : ''}`).join('\n')
          : '无错误';
        logInfo(`Browser test report ${payload.url}: ${errorText}`);
        sendTaskActivity({ description: '已收到浏览器测试报告', status: payload.errors.length ? 'failed' : 'completed' });
      },
      onNativeMessage: (message) => {
        logInfo(`Native message from extension: ${message.type || 'unknown'}`);
        if (message.type === 'clip') {
          const summary = [message.title, message.url, message.selection, message.bodyText]
            .filter((v) => typeof v === 'string')
            .join('\n\n');
          sendChatMessage({ role: 'user', content: `从浏览器扩展抓取的网页内容：\n\n${summary}` });
        } else if (message.type === 'test-report') {
          const errors = Array.isArray(message.errors) ? message.errors : [];
          const errorText = errors.length
            ? errors.map((e: any) => `- ${e.message}${e.source ? ` (${e.source}:${e.line})` : ''}`).join('\n')
            : '无错误';
          const interactions = Array.isArray(message.interactions)
            ? message.interactions.map((i: any) => `[${i.action}] ${i.target || i.tag || ''}${i.value ? ` = ${i.value}` : ''}`).join('\n')
            : '';
          const metrics = (message.metrics || {}) as Record<string, unknown>;
          logInfo(`Native browser test report ${message.url}: ${String(metrics.domNodes || 'unknown')} nodes; ${interactions}; ${errorText}`);
          sendTaskActivity({ description: '已收到浏览器测试报告', status: errors.length ? 'failed' : 'completed' });
        } else {
          logInfo(`Ignored extension message: ${JSON.stringify(message).slice(0, 500)}`);
        }
      },
    });
    extensionServer = ext.server;
    logInfo(`Extension server listening on port ${ext.port}`);

    const extensionIds = (process.env.KYROZEN_EXTENSION_IDS || '').split(',').map((s) => s.trim()).filter(Boolean);
    if (extensionIds.length) {
      await registerNativeMessagingHost(extensionIds);
      logInfo(`Registered native messaging host for extension IDs: ${extensionIds.join(', ')}`);
    }
  } catch (err: any) {
    logError(`Failed to start extension server: ${err.message || err}`);
  }

  const protocolUrl = getProtocolUrl();
  logInfo(`Protocol URL: ${protocolUrl ? redactProtocolUrl(protocolUrl) : 'none'}`);
  if (protocolUrl && mainWindow) {
    mainWindow.webContents.once('did-finish-load', () => {
      void handleProtocolUrl(protocolUrl);
    });
  } else if (onboardingConfig.completed) {
    // Onboarding already completed: try to resume the previous session from encrypted storage.
    const credentials = await loadCredentials();
    if (credentials) {
      serverUrl = normalizeServerUrl(credentials.serverUrl);
      setUpdateApiBaseUrl(serverUrl);
      wsUrl = getWebSocketUrlFromHttp(serverUrl);
      accessToken = credentials.accessToken;
      let resumeWsToken = credentials.wsToken;
      let sessionExpired = false;
      // WebSocket tokens are process-local on the API server. Exchange the
      // persisted JWT on every launch so server restarts recover automatically.
      if (credentials.accessToken && credentials.accessToken.split('.').length === 3) {
        try {
          const verify = await apiPost('/api/desktop/verify-token', {
            access_token: credentials.accessToken,
            device_name: os.hostname(),
            client_version: app.getVersion(),
            platform: process.platform,
          });
          if (verify.ws_token) {
            resumeWsToken = verify.ws_token;
            await saveCredentials(
              resumeWsToken,
              credentials.refreshToken || verify.refresh_token || undefined,
              credentials.accessToken,
            );
          }
        } catch (err: any) {
          if (err?.status === 401 || err?.status === 403) {
            // Supabase access tokens are short-lived. Refresh once before
            // treating the saved login as dead; otherwise a healthy long-lived
            // GitHub session turns into an empty project list after expiry.
            const refreshed = await refreshAccessToken();
            if (refreshed && accessToken) {
              try {
                const verify = await apiPost('/api/desktop/verify-token', {
                  access_token: accessToken,
                  device_name: os.hostname(),
                  client_version: app.getVersion(),
                  platform: process.platform,
                });
                if (verify.ws_token) {
                  resumeWsToken = verify.ws_token;
                  const refreshed = await loadCredentials();
                  await saveCredentials(
                    resumeWsToken,
                    refreshed?.refreshToken || credentials.refreshToken || undefined,
                    accessToken,
                  );
                }
              } catch (refreshErr: any) {
                sessionExpired = true;
                logWarn(`Refreshed session could not be verified: ${refreshErr.message || refreshErr}`);
              }
            } else if (refreshTokenInvalid || !credentials.refreshToken) {
              sessionExpired = true;
              logWarn('Stored session refresh failed; requiring re-login');
            } else {
              logWarn('Stored session refresh was temporarily unavailable; keeping credentials for retry');
            }
          } else {
            logWarn(`Could not refresh desktop session; trying stored token: ${err.message || err}`);
          }
        }
      }
      if (sessionExpired) {
        accessToken = null;
        currentWsToken = null;
        clearSessionRefreshTimer();
        await clearCredentials();
        const notifySessionExpired = () => {
          mainWindow?.webContents.send('kyrozen:session-expired', '登录已过期，请重新登录。');
        };
        if (mainWindow?.webContents.isLoading()) {
          mainWindow.webContents.once('did-finish-load', notifySessionExpired);
        } else {
          notifySessionExpired();
        }
      } else {
        currentWsToken = resumeWsToken;
        connectWebSocket(resumeWsToken);
        scheduleSessionRefresh();
        void fetchGitHubToken();
        const notifySessionResumed = () => {
          mainWindow?.webContents.send('kyrozen:session-resumed', resumeWsToken, credentials.serverUrl);
        };
        if (mainWindow?.webContents.isLoading()) {
          mainWindow.webContents.once('did-finish-load', notifySessionResumed);
        } else {
          notifySessionResumed();
        }
      }
    }
  } else {
    logInfo('Onboarding not completed; waiting for renderer wizard');
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  process.on('uncaughtException', (err) => {
    const summary = `Uncaught exception: ${err.message}\n${err.stack || ''}`;
    logError(summary);
    void promptAndUploadErrorReport(summary);
  });

  process.on('unhandledRejection', (reason) => {
    const summary = reason instanceof Error ? `Unhandled rejection: ${reason.message}\n${reason.stack || ''}` : `Unhandled rejection: ${String(reason)}`;
    logError(summary);
    void promptAndUploadErrorReport(summary);
  });
});

app.on('open-url', (_event, url) => {
  if (mainWindow?.webContents.isLoading()) {
    mainWindow.webContents.once('did-finish-load', () => {
      void handleProtocolUrl(url);
    });
  } else {
    void handleProtocolUrl(url);
  }
});

app.on('before-quit', () => {
  // Allow windows to close normally once a real quit sequence has started.
  isQuitting = true;
});

app.on('window-all-closed', () => {
  disconnectWebSocket();
  stopPythonAgent();
  stopUpdateChecks();
  stopHardwareToolchainAutoUpdate();
  extensionServer?.close();
  if (process.platform !== 'darwin') app.quit();
});

let accessRefreshPromise: Promise<boolean> | null = null;
let websocketTokenRefreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (accessRefreshPromise) return accessRefreshPromise;
  accessRefreshPromise = (async () => {
    try {
      const credentials = await loadCredentials();
      if (!credentials?.refreshToken) {
        refreshTokenInvalid = true;
        return false;
      }
      const response = await fetch(`${serverUrl}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: credentials.refreshToken }),
      });
      if (!response.ok) {
        // 400/401 means the user must authenticate again. Other failures are
        // transient and should leave the persisted session intact for retry.
        refreshTokenInvalid = response.status === 400 || response.status === 401;
        return false;
      }
      const data = await response.json() as { access_token?: string; refresh_token?: string };
      if (!data.access_token) return false;
      accessToken = data.access_token;
      refreshTokenInvalid = false;
      await saveCredentials(
        currentWsToken || credentials.wsToken,
        data.refresh_token || credentials.refreshToken,
        data.access_token,
      );
      logInfo('Refreshed expired API session');
      scheduleSessionRefresh();
      return true;
    } catch (err: any) {
      logWarn(`Failed to refresh API session: ${err.message || err}`);
      return false;
    } finally {
      accessRefreshPromise = null;
    }
  })();
  return accessRefreshPromise;
}

async function reconnectWithFreshWebSocketToken(): Promise<boolean> {
  if (websocketTokenRefreshPromise) return websocketTokenRefreshPromise;
  websocketTokenRefreshPromise = (async () => {
    try {
      const verifyCurrentAccessToken = async () => {
        if (!accessToken) return null;
        return apiPost('/api/desktop/verify-token', {
          access_token: accessToken,
          device_name: os.hostname(),
          client_version: app.getVersion(),
          platform: process.platform,
        });
      };
      let verified: any;
      try {
        verified = await verifyCurrentAccessToken();
      } catch (err: any) {
        if ((err?.status === 401 || err?.status === 403) && await refreshAccessToken()) {
          verified = await verifyCurrentAccessToken();
        } else {
          throw err;
        }
      }
      if (!verified?.ws_token) throw new Error('服务器未返回新的桌面连接凭据');
      const credentials = await loadCredentials();
      currentWsToken = String(verified.ws_token);
      await saveCredentials(
        currentWsToken,
        credentials?.refreshToken || verified.refresh_token || undefined,
        accessToken || undefined,
      );
      connectWebSocket(currentWsToken);
      return true;
    } catch (err: any) {
      logWarn(`Failed to renew WebSocket token: ${err.message || err}`);
      updateConnection('error', refreshTokenInvalid ? '登录已失效，请重新登录' : '云端暂时不可用，正在自动恢复');
      if (refreshTokenInvalid) {
        mainWindow?.webContents.send('kyrozen:session-expired', '登录已过期，请重新登录。');
      } else {
        logWarn('WebSocket renewal failed transiently; retaining persisted session');
        sessionRefreshTimer = setTimeout(scheduleSessionRefresh, SESSION_REFRESH_FALLBACK_MS);
      }
      return false;
    } finally {
      websocketTokenRefreshPromise = null;
    }
  })();
  return websocketTokenRefreshPromise;
}

async function apiGet(endpoint: string, auth = true) {
  const headers: Record<string, string> = {};
  if (auth && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  let response = await fetch(`${serverUrl}${endpoint}`, { headers });
  if (auth && (response.status === 401 || response.status === 403) && await refreshAccessToken()) {
    response = await fetch(`${serverUrl}${endpoint}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  }
  if (!response.ok) {
    // Token expired or invalid — clear it so we don't keep using it.
    if (response.status === 401 || response.status === 403) {
      accessToken = null;
    }
    const text = await response.text();
    const error = new Error(text || `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function apiPost(endpoint: string, body: unknown, auth = false) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  let response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (auth && (response.status === 401 || response.status === 403) && await refreshAccessToken()) {
    response = await fetch(`${serverUrl}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      accessToken = null;
    }
    const text = await response.text();
    const error = new Error(text || `HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function apiPatch(endpoint: string, body: unknown) {
  let response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if ((response.status === 401 || response.status === 403) && await refreshAccessToken()) {
    response = await fetch(`${serverUrl}${endpoint}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
  }
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json();
}

async function apiPut(endpoint: string, body: unknown) {
  let response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if ((response.status === 401 || response.status === 403) && await refreshAccessToken()) {
    response = await fetch(`${serverUrl}${endpoint}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
  }
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json();
}

async function apiDelete(endpoint: string) {
  let response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'DELETE',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if ((response.status === 401 || response.status === 403) && await refreshAccessToken()) {
    response = await fetch(`${serverUrl}${endpoint}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  }
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json();
}

interface AuditEvent {
  projectId?: string;
  taskId?: string;
  tool: string;
  action: string;
  parameters?: Record<string, unknown>;
  confirmed: boolean;
  fullTrust: boolean;
}

async function logAuditEvent(event: AuditEvent): Promise<void> {
  if (!accessToken) return;
  try {
    await apiPost(
      '/api/events',
      {
        event_type: 'desktop.audit',
        project_id: event.projectId || currentProjectId,
        payload: {
          task_id: event.taskId,
          tool: event.tool,
          action: event.action,
          parameters: event.parameters,
          confirmed: event.confirmed,
          full_trust: event.fullTrust,
          source: 'desktop',
        },
        session_id: accessToken.slice(-16),
      },
      true,
    );
  } catch (err: any) {
    logError(`Audit log failed: ${err.message || String(err)}`);
  }
}

interface ArtifactSummary {
  id: string;
  type: string;
  title: string;
  version: number;
  updated_at: string;
}

interface ArtifactFull extends ArtifactSummary {
  content: string;
}

interface LocalManifestEntry {
  id: string;
  type: string;
  title: string;
  version: number;
  local_path: string;
  updated_at: string;
}

async function loadLocalManifest(contextDir: string): Promise<LocalManifestEntry[]> {
  try {
    const raw = await fs.readFile(path.join(contextDir, 'manifest.json'), 'utf-8');
    const parsed = JSON.parse(raw) as LocalManifestEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Download the latest cloud artifacts for a project into <workspace>/.kyrozen/context/. */
async function syncProjectArtifacts(projectId: string): Promise<void> {
  const root = workspaceMap[projectId];
  if (!root || !accessToken) return;

  try {
    const artifacts: ArtifactSummary[] = await apiGet(`/api/projects/${projectId}/artifacts`);
    const contextDir = path.join(root, '.kyrozen', 'context');
    await fs.mkdir(contextDir, { recursive: true });

    const localManifest = await loadLocalManifest(contextDir);
    const localByTitle = new Map(localManifest.map((entry) => [entry.title, entry]));

    const conflicts: { title: string; cloudUpdatedAt: string; localUpdatedAt: string }[] = [];
    for (const summary of artifacts) {
      const localEntry = localByTitle.get(summary.title);
      if (localEntry && new Date(localEntry.updated_at) > new Date(summary.updated_at)) {
        conflicts.push({
          title: summary.title,
          cloudUpdatedAt: summary.updated_at,
          localUpdatedAt: localEntry.updated_at,
        });
      }
    }

    let useCloudForConflicts = true;
    if (conflicts.length > 0 && mainWindow) {
      const detail = conflicts.map((c) => `• ${c.title}`).join('\n');
      const result = await dialog.showMessageBox(mainWindow, {
        type: 'warning',
        buttons: ['使用云端版本', '保留本地版本'],
        defaultId: 0,
        cancelId: 1,
        title: 'Artifact 云本地冲突',
        message: `检测到 ${conflicts.length} 个 Artifact 本地版本比云端更新，请选择处理方式`,
        detail,
      });
      useCloudForConflicts = result.response === 0;
    }

    const manifest: Array<Record<string, unknown>> = [];
    for (const summary of artifacts) {
      const full: ArtifactFull = await apiGet(`/api/projects/${projectId}/artifacts/${summary.id}`);
      const safeTitle = String(full.title || full.type).replace(/[^a-zA-Z0-9\u4e00-\u9fa5._-]/g, '_');
      const fileName = `${safeTitle}.md`;
      const filePath = path.join(contextDir, fileName);
      const isConflict = conflicts.some((c) => c.title === full.title);
      if (isConflict && !useCloudForConflicts) {
        // Keep local version; still update manifest metadata from cloud.
        manifest.push({
          id: full.id,
          type: full.type,
          title: full.title,
          version: full.version,
          local_path: filePath,
          updated_at: full.updated_at,
          conflict: 'kept_local',
        });
        continue;
      }
      await fs.writeFile(filePath, full.content || '', 'utf-8');
      manifest.push({
        id: full.id,
        type: full.type,
        title: full.title,
        version: full.version,
        local_path: filePath,
        updated_at: full.updated_at,
      });
    }

    await fs.writeFile(path.join(contextDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
    sendTaskActivity({ description: `已同步 ${artifacts.length} 个项目资料`, status: 'completed' });
  } catch (err: any) {
    logWarn(`Artifact sync failed: ${err.message || err}`);
  }
}

const KEY_FILE_RE = /(^|\/)(package\.json|readme[^/]*|\.env[^/]*|tsconfig\.json|vite\.config\.[jt]s|tailwind\.config\.[jt]s)$/i;
const SOURCE_FILE_RE = /\.(js|jsx|ts|tsx|py|html|css|vue|svelte)$/i;
const IGNORED_PATH_SEGMENTS = new Set(['.kyrozen', 'node_modules', '.git', 'dist', 'build']);

function isIgnoredRelativePath(relativePath: string): boolean {
  return relativePath.split(/[\\/]/).some((segment) => IGNORED_PATH_SEGMENTS.has(segment));
}

function shouldUploadFileSummary(relativePath: string): boolean {
  if (isIgnoredRelativePath(relativePath)) return false;
  const lower = relativePath.toLowerCase();
  if (KEY_FILE_RE.test(lower)) return true;
  if (SOURCE_FILE_RE.test(lower)) return true;
  return false;
}

function sanitizeFileSnippet(snippet: string): string {
  return snippet
    .replace(/\b(sk-[a-zA-Z0-9]{20,})\b/g, '<API_KEY>')
    .replace(/\b([A-Za-z0-9_\-]{32,})\b/g, '<TOKEN>')
    .replace(/(password|secret|token|key)\s*=\s*[^\s\n]+/gi, '$1=<REDACTED>')
    .replace(/(https?:\/\/[^\s\"]+:[^@\s\"]+@)/g, 'https://<CREDENTIALS>@');
}

async function uploadFileSummary(
  projectId: string,
  absolutePath: string,
  eventType: string,
): Promise<void> {
  if (!accessToken) return;
  const root = workspaceMap[projectId];
  if (!root) return;

  let event: string = eventType === 'rename' ? 'created' : 'changed';
  let summary = '';
  let snippet = '';
  try {
    const stats = await fs.stat(absolutePath);
    if (!stats.isFile()) return;
    const content = await fs.readFile(absolutePath, 'utf-8');
    summary = `File ${event}: ${path.relative(root, absolutePath)}`;
    const rawSnippet = content.length > 4000 ? content.slice(0, 4000) + '\n...' : content;
    snippet = sanitizeFileSnippet(rawSnippet);
  } catch {
    event = 'deleted';
    summary = `File deleted: ${path.relative(root, absolutePath)}`;
  }

  try {
    await apiPost(
      `/api/projects/${projectId}/file-summaries`,
      { file_path: absolutePath, event, summary, content_snippet: snippet },
      true,
    );
  } catch (err: any) {
    logWarn(`File summary sync failed: ${err.message || err}`);
  }
}

function startWatchingProjectFiles(projectId: string, root: string): void {
  stopWatchingProjectFiles(projectId);
  try {
    const watcher = watch(
      root,
      { recursive: true },
      (eventType, filename) => {
        if (!filename) return;
        const absolute = path.join(root, filename);
        const relative = path.relative(root, absolute);
        if (!shouldUploadFileSummary(relative)) return;
        const key = `${projectId}:${absolute}`;
        const existing = pendingFileChanges.get(key);
        if (existing) clearTimeout(existing);
        pendingFileChanges.set(
          key,
          setTimeout(() => {
            pendingFileChanges.delete(key);
            void uploadFileSummary(projectId, absolute, String(eventType));
          }, 1500),
        );

        // Debounce auto-commit for the whole project.
        const existingAutoCommit = pendingAutoCommit.get(projectId);
        if (existingAutoCommit) clearTimeout(existingAutoCommit);
        pendingAutoCommit.set(
          projectId,
          setTimeout(() => {
            pendingAutoCommit.delete(projectId);
            void maybeAutoCommit(root, githubAccessToken);
          }, 10000),
        );
      },
    );
    projectFileWatchers.set(projectId, watcher);
  } catch (err: any) {
    logWarn(`Project file watcher failed: ${err.message || err}`);
  }
}

function stopWatchingProjectFiles(projectId: string): void {
  const watcher = projectFileWatchers.get(projectId);
  if (watcher) {
    watcher.close();
    projectFileWatchers.delete(projectId);
  }
}

ipcMain.handle('kyrozen:login', async (_event, email: string, password: string, url: string) => {
  logInfo(`Login requested for ${email} at ${url}`);
  try {
    serverUrl = normalizeServerUrl(url);
    setUpdateApiBaseUrl(serverUrl);
    wsUrl = getWebSocketUrlFromHttp(serverUrl);
    logInfo(`Signing in via ${serverUrl}`);
    const data = await apiPost('/api/auth/signin', { email, password });
    if (!data.access_token) {
      return { success: false, error: '登录失败：未返回 access_token' };
    }

    const verify = await apiPost('/api/desktop/verify-token', {
      access_token: data.access_token,
      device_name: os.hostname(),
      client_version: app.getVersion(),
      platform: process.platform,
    });
    accessToken = data.access_token;
    logInfo(`Signin success, verifying desktop token`);
    await saveCredentials(verify.ws_token, data.refresh_token || verify.refresh_token, accessToken || undefined);
    refreshTokenInvalid = false;
    scheduleSessionRefresh();
    connectWebSocket(verify.ws_token);
    void fetchGitHubToken();
    logInfo(`Login complete, wsToken acquired`);
    return { success: true, wsToken: verify.ws_token };
  } catch (err: any) {
    logError(`Login failed: ${err.message || err}`);
    return { success: false, error: err.message || '登录失败' };
  }
});

ipcMain.handle('kyrozen:start-pairing', async (_event, url: string) => {
  try {
    const baseUrl = url.replace(/\/$/, '');
    const response = await fetch(`${baseUrl}/api/desktop/pairing-code`, { method: 'POST' });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    const data = await response.json();
    return { success: true, code: data.code, expiresIn: data.expires_in };
  } catch (err: any) {
    return { success: false, error: err.message || '获取配对码失败' };
  }
});

ipcMain.handle('kyrozen:poll-pairing', async (_event, url: string, code: string) => {
  try {
    const baseUrl = url.replace(/\/$/, '');
    const response = await fetch(`${baseUrl}/api/desktop/poll-pairing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    const data = await response.json();
    if (data.ready && data.ws_token) {
      serverUrl = normalizeServerUrl(baseUrl);
      setUpdateApiBaseUrl(serverUrl);
      wsUrl = getWebSocketUrlFromHttp(serverUrl);
      accessToken = data.access_token || null;
      await saveCredentials(data.ws_token, undefined, accessToken || undefined);
      refreshTokenInvalid = !data.access_token;
      scheduleSessionRefresh();
      connectWebSocket(data.ws_token);
      return { success: true, wsToken: data.ws_token };
    }
    return { success: true, ready: false };
  } catch (err: any) {
    return { success: false, error: err.message || '轮询配对失败' };
  }
});

ipcMain.handle('kyrozen:verify-open-token', async (_event, token: string) => {
  logInfo('Verifying open token from URL scheme');
  try {
    const data = await apiPost('/api/desktop/verify-token', {
      token,
      device_name: os.hostname(),
      client_version: app.getVersion(),
      platform: process.platform,
    });
    accessToken = data.access_token || null;
    logInfo(`Open token verified, wsToken acquired`);
    setUpdateApiBaseUrl(serverUrl);
    await saveCredentials(data.ws_token, data.refresh_token, accessToken || undefined);
    refreshTokenInvalid = false;
    scheduleSessionRefresh();
    await saveOnboardingConfig({ completed: true, completedAt: new Date().toISOString() });
    connectWebSocket(data.ws_token);
    void fetchGitHubToken();
    return { wsToken: data.ws_token, refreshToken: data.refresh_token };
  } catch (err: any) {
    logError(`Open token verification failed: ${err.message || err}`);
    updateConnection('error', err.message || '令牌验证失败');
    return null;
  }
});

async function ensureWorkspaceStructure(root: string): Promise<void> {
  await fs.mkdir(path.join(root, 'software'), { recursive: true });
  await fs.mkdir(path.join(root, 'hardware'), { recursive: true });
  await fs.mkdir(path.join(root, 'documents'), { recursive: true });
  await fs.mkdir(path.join(root, 'logs'), { recursive: true });
  await fs.mkdir(path.join(root, '.kyrozen', 'context'), { recursive: true });
}

ipcMain.handle('kyrozen:set-current-project', async (_event, projectId: string) => {
  if (currentProjectId && currentProjectId !== projectId) {
    stopWatchingProjectFiles(currentProjectId);
  }
  currentProjectId = projectId;
  const root = await getWorkspaceRoot(projectId);
  if (root) {
    await ensureWorkspaceStructure(root);
    sendTaskActivity({ description: '正在准备项目工作区' });
    await syncProjectArtifacts(projectId);
    startWatchingProjectFiles(projectId, root);
  }
  wsClient?.send(JSON.stringify({ type: 'heartbeat', active_project_id: projectId }));
  return { workspaceRoot: root };
});

ipcMain.handle('kyrozen:pick-workspace', async (_event, projectId: string) => {
  const root = await pickWorkspaceRoot(projectId);
  return { workspaceRoot: root };
});

ipcMain.handle('kyrozen:get-workspace-root', async (_event, projectId: string) => {
  return { workspaceRoot: await getWorkspaceRoot(projectId) };
});

// P0-R6: read the real .kyrozen/PLAN.json for a workspace so the renderer
// can hydrate the task panel on project open or after a reload.
ipcMain.handle('kyrozen:read-workspace-plan', async (_event, workspaceRoot: string) => {
  if (!workspaceRoot || typeof workspaceRoot !== 'string') {
    return { success: false, plan: null, error: 'Invalid workspace root' };
  }
  try {
    const planPath = path.join(workspaceRoot, '.kyrozen', 'PLAN.json');
    try {
      await fs.access(planPath);
    } catch {
      return { success: true, plan: null };
    }
    const raw = await fs.readFile(planPath, 'utf-8');
    const plan = JSON.parse(raw);
    return { success: true, plan };
  } catch (err: any) {
    logWarn(`Failed to read PLAN.json for ${workspaceRoot}: ${err?.message || err}`);
    return { success: false, plan: null, error: err?.message || String(err) };
  }
});

async function isPathInside(parent: string, target: string): Promise<boolean> {
  async function resolveWithExistingAncestor(input: string): Promise<string> {
    let cursor = path.resolve(input);
    const missing: string[] = [];
    while (true) {
      try {
        const real = await fs.realpath(cursor);
        return path.join(real, ...missing.reverse());
      } catch {
        const parentDir = path.dirname(cursor);
        if (parentDir === cursor) return path.resolve(input);
        missing.push(path.basename(cursor));
        cursor = parentDir;
      }
    }
  }

  const [realParent, realTarget] = await Promise.all([
    resolveWithExistingAncestor(parent),
    resolveWithExistingAncestor(target),
  ]);
  const relative = path.relative(realParent, realTarget);
  return !relative.startsWith('..') && !path.isAbsolute(relative);
}

async function listWorkspaceFiles(projectId: string): Promise<string[]> {
  const root = workspaceMap[projectId];
  if (!root) return [];
  const files: string[] = [];
  async function walk(dir: string, prefix: string) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (isIgnoredRelativePath(rel)) continue;
      if (entry.isDirectory()) {
        await walk(full, rel);
      } else if (entry.isFile()) {
        files.push(rel);
      }
    }
  }
  await walk(root, '');
  return files;
}

ipcMain.handle('kyrozen:list-files', async (_event, projectId: string) => {
  try {
    return { files: await listWorkspaceFiles(projectId) };
  } catch (err: any) {
    logError(`Failed to list files: ${err.message || err}`);
    return { files: [], error: err.message || String(err) };
  }
});

interface SearchResult {
  projectId: string;
  relativePath: string;
  matchType: 'filename' | 'content';
  snippet?: string;
}

async function searchAcrossProjects(query: string, options?: { maxResults?: number; includeContent?: boolean }): Promise<SearchResult[]> {
  const normalizedQuery = query.toLowerCase().trim();
  if (!normalizedQuery) return [];
  const maxResults = options?.maxResults ?? 50;
  const includeContent = options?.includeContent ?? true;
  const results: SearchResult[] = [];

  for (const [projectId, root] of Object.entries(workspaceMap)) {
    if (results.length >= maxResults) break;
    try {
      const files = await listWorkspaceFiles(projectId);
      for (const relativePath of files) {
        if (results.length >= maxResults) break;
        if (isIgnoredRelativePath(relativePath)) continue;

        if (relativePath.toLowerCase().includes(normalizedQuery)) {
          results.push({ projectId, relativePath, matchType: 'filename' });
          continue;
        }

        if (!includeContent) continue;
        const absolutePath = path.join(root, relativePath);
        try {
          const stats = await fs.stat(absolutePath);
          if (!stats.isFile() || stats.size > 1024 * 1024) continue;
          const content = await fs.readFile(absolutePath, 'utf-8');
          const lowerContent = content.toLowerCase();
          const index = lowerContent.indexOf(normalizedQuery);
          if (index !== -1) {
            const start = Math.max(0, index - 60);
            const end = Math.min(content.length, index + normalizedQuery.length + 60);
            results.push({
              projectId,
              relativePath,
              matchType: 'content',
              snippet: `...${content.slice(start, end)}...`,
            });
          }
        } catch {
          // ignore unreadable files
        }
      }
    } catch (err: any) {
      logError(`Failed to search project ${projectId}: ${err.message || err}`);
    }
  }

  return results;
}

ipcMain.handle('kyrozen:search-across-projects', async (_event, query: string, options?: { maxResults?: number; includeContent?: boolean }) => {
  try {
    const results = await searchAcrossProjects(query, options);
    return { results };
  } catch (err: any) {
    logError(`Cross-project search failed: ${err.message || err}`);
    return { results: [], error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:read-file', async (_event, projectId: string, relativePath: string) => {
  try {
    const root = workspaceMap[projectId];
    if (!root) return { content: '', error: 'No workspace mapped' };
    const target = path.resolve(root, relativePath);
    if (!(await isPathInside(root, target))) {
      return { content: '', error: 'Path outside workspace' };
    }
    const content = await fs.readFile(target, 'utf-8');
    return { content };
  } catch (err: any) {
    return { content: '', error: err.message || String(err) };
  }
});

const SENSITIVE_PLACEHOLDER_RE = /\b(API_KEY|API_SECRET|API_TOKEN|SECRET_KEY|PRIVATE_KEY|PASSWORD|DB_PASSWORD|DATABASE_URL|TOKEN)\b\s*[=:]/i;

function hasSensitivePlaceholder(content: string): boolean {
  return SENSITIVE_PLACEHOLDER_RE.test(content);
}

function sanitizeEnvExample(content: string): string {
  return content
    .split(/\r?\n/)
    .map((line) => {
      if (!line.trim() || line.trimStart().startsWith('#')) return line;
      const match = line.match(/^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*)(.*)$/);
      if (!match) return line;
      const value = match[2].trim();
      if (!value || /^(?:<[^>]+>|your[-_]|replace|changeme|example)/i.test(value)) return line;
      return `${match[1]}<REPLACE_ME>`;
    })
    .join('\n');
}

async function ensureGitignoreEnv(root: string): Promise<void> {
  const gitignorePath = path.join(root, '.gitignore');
  let existing = '';
  try {
    existing = await fs.readFile(gitignorePath, 'utf-8');
  } catch {
    // file may not exist
  }
  if (/^\.env$/m.test(existing)) return;
  const updated = existing ? `${existing.trim()}\n.env\n` : '.env\n';
  await fs.writeFile(gitignorePath, updated, 'utf-8');
}

async function showEnvWarning(): Promise<void> {
  await dialog.showMessageBox(mainWindow!, {
    type: 'warning',
    buttons: ['我知道了'],
    defaultId: 0,
    title: '敏感信息提醒',
    message: '检测到环境配置文件',
    detail: '.env 已加入 .gitignore；.env.example 中的实际值会替换为 <REPLACE_ME>，避免密钥被提交。',
  });
}

ipcMain.handle('kyrozen:save-file', async (_event, projectId: string, relativePath: string, content: string) => {
  try {
    const root = workspaceMap[projectId];
    if (!root) return { success: false, error: 'No workspace mapped' };

    let targetRelative = relativePath;
    let contentToWrite = content;
    let shouldWarn = false;

    // Keep real values in ignored .env files and scrub examples before writing.
    if (path.basename(relativePath) === '.env' && hasSensitivePlaceholder(content)) {
      shouldWarn = true;
    } else if (path.basename(relativePath).endsWith('.env.example') && hasSensitivePlaceholder(content)) {
      contentToWrite = sanitizeEnvExample(content);
      shouldWarn = true;
    }

    const target = path.resolve(root, targetRelative);
    if (!(await isPathInside(root, target))) {
      return { success: false, error: 'Path outside workspace' };
    }
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, contentToWrite, 'utf-8');

    if (shouldWarn) {
      await ensureGitignoreEnv(root);
      void showEnvWarning();
    }

    return { success: true, savedPath: targetRelative };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

async function localProjectName(root: string, projectId: string): Promise<string> {
  if (workspaceNames[projectId]) return workspaceNames[projectId];
  try {
    for (const rel of ['README.md', 'docs/PROBLEM.md', 'PROBLEM.md']) {
      const p = path.join(root, rel);
      try {
        const text = await fs.readFile(p, 'utf-8');
        const m = text.match(/^#\s+(.+)$/m);
        if (m) {
          // Strip a leading stage-label prefix (e.g. "问题定义：", "产品定义：")
          // so the project name is the real title, not a gate-item label.
          const name = String(m[1].trim()).replace(
            /^(问题定义|问题陈述|产品定义|产品方案|技术方案|解决方案|市场调研|需求定义)[：:]\s*/,
            '',
          ).trim();
          if (name) return name.slice(0, 60);
        }
      } catch { /* not present */ }
    }
  } catch { /* ignore */ }
  return `本地项目 ${projectId.slice(0, 8)}`;
}

ipcMain.handle('kyrozen:get-projects', async () => {
  let cloud: Record<string, unknown>[] = [];
  if (accessToken) {
    try {
      const list = await apiGet('/api/projects');
      cloud = Array.isArray(list) ? (list as Record<string, unknown>[]) : [];
    } catch (err: any) {
      logError(`Failed to load projects: ${err.message || err}`);
    }
  }
  // P0-R4/P0-R10: the sidebar must reflect locally-known workspaces even before
  // (or without) a cloud sync, so the list is never empty while the Git panel
  // already shows a connected local repo. Union cloud projects with the local
  // workspace map, de-duplicated by project id (cloud entry wins when present).
  const cloudIds = new Set(cloud.map((p) => String(p.id)));
  const merged: Record<string, unknown>[] = [...cloud];
  for (const [pid, root] of Object.entries(workspaceMap)) {
    if (cloudIds.has(pid)) continue;
    merged.push({
      id: pid,
      name: await localProjectName(String(root), pid),
      local_only: true,
      workspace_root: root,
    });
  }
  logInfo(`Loaded ${merged.length} projects (cloud ${cloud.length}, local ${merged.length - cloud.length})`);
  return merged;
});

ipcMain.handle('kyrozen:create-project', async (_event, name: string, description?: string, goal?: string) => {
  if (!accessToken) {
    return { success: false, error: '未登录' };
  }
  try {
    const project = await apiPost('/api/projects', {
      name,
      description: description || '',
      goal: goal || '',
      initial_idea: goal || description || '',
    }, true);
    logInfo(`Created project: ${project.id} - ${project.name}`);
    return { success: true, project };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:rename-project', async (_event, projectId: string, name: string) => {
  const trimmed = String(name || '').trim();
  if (!trimmed) return { success: false, error: '项目名称不能为空' };
  if (trimmed.length > 80) return { success: false, error: '项目名称不能超过 80 个字符' };
  try {
    if (projectId.startsWith('local_')) {
      if (!workspaceMap[projectId]) return { success: false, error: '本地项目不存在' };
      workspaceNames[projectId] = trimmed;
      await saveWorkspaceNames();
      return { success: true, project: { id: projectId, name: trimmed } };
    }
    const project = await apiPut(`/api/projects/${encodeURIComponent(projectId)}`, { name: trimmed });
    return { success: true, project };
  } catch (err: any) {
    return { success: false, error: err.message || '重命名失败' };
  }
});

ipcMain.handle('kyrozen:open-project-in-finder', async (_event, projectId: string) => {
  try {
    const root = await getWorkspaceRoot(projectId);
    if (!root) return { success: false, error: '项目没有本地工作区' };
    const error = await shell.openPath(root);
    return error ? { success: false, error } : { success: true, workspaceRoot: root };
  } catch (err: any) {
    return { success: false, error: err.message || '无法在 Finder 中打开项目' };
  }
});

ipcMain.handle('kyrozen:delete-project', async (_event, projectId: string) => {
  try {
    if (!projectId.startsWith('local_')) {
      await apiDelete(`/api/projects/${encodeURIComponent(projectId)}`);
    }
    if (currentProjectId === projectId) {
      stopWatchingProjectFiles(projectId);
      currentProjectId = null;
    }
    delete workspaceMap[projectId];
    delete workspaceNames[projectId];
    await Promise.all([saveWorkspaceMap(), saveWorkspaceNames()]);
    logInfo(`Deleted project ${projectId}; local workspace was preserved`);
    return { success: true, projectId, localWorkspacePreserved: true };
  } catch (err: any) {
    return { success: false, error: err.message || '删除项目失败' };
  }
});

ipcMain.handle('kyrozen:get-project-state', async (_event, projectId: string) => {
  if (!accessToken) return null;
  try {
    return await apiGet(`/api/projects/${projectId}/state`);
  } catch (err: any) {
    logError(`Failed to get project state: ${err.message || err}`);
    return null;
  }
});

const PROJECT_WORKSPACE_SECTIONS = {
  discovery: 'problem-discovery',
  research: 'market-research',
  planning: 'planning',
  development: 'development',
  hardware: 'hardware',
  testing: 'testing',
  learning: 'learning',
  improvement: 'improvement',
} as const;

async function loadLocalProjectSummary(projectId: string): Promise<Record<string, unknown>> {
  const root = workspaceMap[projectId];
  if (!root) return { files: [], deliverables: [], software: null, stagegate: null };
  const readJson = async (relative: string): Promise<unknown> => {
    try { return JSON.parse(await fs.readFile(path.join(root, relative), 'utf-8')); }
    catch { return null; }
  };
  const files = await listWorkspaceFiles(projectId).catch(() => []);
  return {
    workspace_root: root,
    files,
    deliverables: await readJson('.kyrozen/deliverables.json') || [],
    software: await readJson('.kyrozen/software_feature.json'),
    stagegate: await readJson('.kyrozen/stagegate.json'),
  };
}

async function loadProjectWorkspace(projectId: string): Promise<Record<string, unknown>> {
  const entries = await Promise.all(
    Object.entries(PROJECT_WORKSPACE_SECTIONS).map(async ([key, endpoint]) => [
      key,
      await apiGet(`/api/projects/${projectId}/${endpoint}/state`),
    ]),
  );
  const sections = Object.fromEntries(entries) as Record<string, Record<string, unknown>>;
  const [learningRecords, failureKnowledge, successKnowledge] = await Promise.all([
    apiGet(`/api/projects/${projectId}/learning/records`),
    apiGet(`/api/projects/${projectId}/learning/failures`),
    apiGet(`/api/projects/${projectId}/learning/successes`),
  ]);
  sections.learning = {
    ...(sections.learning || {}),
    learning_records: learningRecords,
    failure_knowledge: failureKnowledge,
    success_knowledge: successKnowledge,
  };
  const [project, state, decisions, artifactSummaries, tasks] = await Promise.all([
    apiGet(`/api/projects/${projectId}`),
    apiGet(`/api/projects/${projectId}/state`),
    apiGet(`/api/projects/${projectId}/decisions`),
    apiGet(`/api/projects/${projectId}/artifacts`),
    apiGet(`/api/projects/${projectId}/tasks`),
  ]);
  const artifacts = await Promise.all(
    (artifactSummaries as Array<Record<string, unknown>>).map((artifact) =>
      apiGet(`/api/projects/${projectId}/artifacts/${String(artifact.id)}`),
    ),
  );
  const local = await loadLocalProjectSummary(projectId);
  return { project, state, decisions, artifacts, tasks, sections, local };
}

ipcMain.handle('kyrozen:get-project-workspace', async (_event, projectId: string) => {
  if (!accessToken) return { success: false, error: '未登录' };
  try {
    return { success: true, data: await loadProjectWorkspace(projectId) };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:create-decision', async (_event, projectId: string, decision: string, reason: string) => {
  try {
    const data = await apiPost(`/api/projects/${projectId}/decisions`, { decision, reason }, true);
    return { success: true, data };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:create-feedback', async (_event, projectId: string, description: string, type: string, priority: string) => {
  try {
    const data = await apiPost('/api/feedback', { project_id: projectId, description, type, priority }, true);
    return { success: true, data };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:update-suggestion-status', async (_event, projectId: string, suggestionId: string, status: string) => {
  try {
    const data = await apiPatch(`/api/projects/${projectId}/learning/suggestions/${suggestionId}/status`, { status });
    return { success: true, data };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:delete-learning-item', async (_event, projectId: string, kind: string, itemId: string) => {
  const endpoints: Record<string, string> = {
    record: 'records',
    failure: 'failures',
    success: 'successes',
    suggestion: 'suggestions',
  };
  const endpoint = endpoints[kind];
  if (!endpoint) return { success: false, error: '未知学习记录类型' };
  try {
    await apiDelete(`/api/projects/${projectId}/learning/${endpoint}/${itemId}`);
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:export-project', async (_event, projectId: string) => {
  try {
    const data = await loadProjectWorkspace(projectId);
    const result = await dialog.showSaveDialog(mainWindow!, {
      title: '导出 Kyrozen 项目',
      defaultPath: `kyrozen-${projectId}.json`,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    });
    if (result.canceled || !result.filePath) return { success: false, cancelled: true };
    await fs.writeFile(result.filePath, JSON.stringify({ exported_at: new Date().toISOString(), ...data }, null, 2), 'utf-8');
    return { success: true, filePath: result.filePath };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:get-quota', async () => {
  if (!accessToken) return { allowed: false, reason: 'Not logged in', used: 0, limit: 0, remaining: 0 };
  try {
    return await apiGet('/api/desktop/quota');
  } catch (err: any) {
    logError(`Failed to fetch quota: ${err.message || err}`);
    return { allowed: false, reason: err.message || 'Quota fetch failed', used: 0, limit: 0, remaining: 0 };
  }
});

ipcMain.handle('kyrozen:get-server-url', () => serverUrl);

ipcMain.handle('kyrozen:set-server-url', async (_event, url: string) => {
  try {
    await saveServerUrl(url);
    return { success: true, serverUrl };
  } catch (err: any) {
    logError(`Failed to set server URL: ${err.message || err}`);
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:get-full-trust', () => {
  return { enabled: fullTrustMode };
});

ipcMain.handle('kyrozen:set-full-trust', async (_event, enabled: boolean) => {
  fullTrustMode = Boolean(enabled);
  logWarn(`Full-trust mode ${fullTrustMode ? 'enabled' : 'disabled'} by user`);
  mainWindow?.webContents.send('kyrozen:full-trust-change', { enabled: fullTrustMode });
  if (fullTrustMode) {
    showNotification(
      '已开启完全信任模式',
      '本次会话内高危工具将自动执行，不再弹出确认对话框。'
    );
    // Record a decision record so the cloud knows this project/user opted into full trust.
    try {
      await apiPost(
        '/api/events',
        {
          event_type: 'desktop.decision_record',
          project_id: currentProjectId,
          payload: {
            decision: 'enable_full_trust',
            source: 'desktop',
            project_id: currentProjectId,
            session_id: accessToken ? accessToken.slice(-16) : null,
          },
          session_id: accessToken ? accessToken.slice(-16) : undefined,
        },
        true,
      );
    } catch (err: any) {
      logError(`Failed to record full-trust decision: ${err.message || err}`);
    }
  }
  return { enabled: fullTrustMode };
});

ipcMain.handle('kyrozen:check-for-updates', async () => {
  try {
    await checkForUpdates();
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:ensure-hardware-toolchain', async () => {
  try {
    const arduino = await ensureArduinoCLI((msg) => sendTaskActivity({ description: msg }));
    const pio = await ensurePlatformIO((msg) => sendTaskActivity({ description: msg }));
    mainWindow?.webContents.send('kyrozen:hardware-tool-status', getToolStatus());
    return {
      success: true,
      arduino: { path: arduino.path, version: arduino.version },
      pio: { path: pio.path, version: pio.version },
    };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:install-common-cores', async () => {
  try {
    await installCommonCores((msg) => sendTaskActivity({ description: msg }));
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:check-hardware-updates', async () => {
  try {
    const results = await checkAndUpdateHardwareToolchain((msg) => sendTaskActivity({ description: msg }));
    mainWindow?.webContents.send('kyrozen:hardware-tool-status', getToolStatus());
    return { success: true, results };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:get-hardware-tool-status', async () => {
  return {
    success: true,
    tools: getToolStatus(),
  };
});

ipcMain.handle('kyrozen:start-github-login', async () => {
  try {
    const data = await apiGet('/api/auth/github/login', false);
    if (data.authorize_url) {
      shell.openExternal(data.authorize_url);
      logInfo('Opened GitHub OAuth login URL in browser');
      return { success: true };
    }
    return { success: false, error: 'No authorize URL returned' };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:connect-github', async () => {
  if (!accessToken) {
    return { success: false, error: 'Not logged in' };
  }
  try {
    const data = await apiGet('/api/auth/github/authorize?desktop=1');
    if (data.authorize_url) {
      shell.openExternal(data.authorize_url);
      return { success: true };
    }
    return { success: false, error: 'No authorize URL returned' };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

function getCurrentWorkspaceRoot(): string | null {
  if (!currentProjectId) return null;
  return workspaceMap[currentProjectId] || null;
}

ipcMain.handle('kyrozen:get-github-status', async () => {
  const base: { connected: boolean; scope?: string; login?: string; avatarUrl?: string; expired?: boolean } = {
    connected: !!githubAccessToken,
    scope: githubTokenScope || undefined,
  };
  if (!githubAccessToken) return base;
  // Validate the token and surface the user's identity (3.5 #2) + expiry (3.5 #1).
  try {
    const resp = await fetch('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${githubAccessToken}`, Accept: 'application/vnd.github+json' },
    });
    if (resp.status === 401) {
      // Token expired or revoked -> guide re-login.
      return { ...base, connected: true, expired: true };
    }
    if (resp.ok) {
      const user = await resp.json() as any;
      return { ...base, connected: true, login: user.login, avatarUrl: user.avatar_url, expired: false };
    }
  } catch {
    // Network error during validation: keep the cached connection state.
  }
  return base;
});

ipcMain.handle('kyrozen:disconnect-github', async () => {
  try {
    // Best-effort: ask the backend to drop the stored token.
    if (accessToken) {
      await apiPost('/api/user/github-token', { token: '', scope: '' }, true).catch(() => undefined);
    }
  } catch { /* ignore backend errors during disconnect */ }
  githubAccessToken = null;
  githubTokenScope = null;
  sendGitHubStatus();
  logInfo('Disconnected GitHub account');
  return { success: true };
});

ipcMain.handle('kyrozen:init-git-repo', async (_event, remoteUrl?: string) => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, error: '未选择项目工作区' };
  }
  const result = await initGitRepo(root, remoteUrl);
  return result;
});

ipcMain.handle('kyrozen:get-git-status', async (_event, projectId?: string) => {
  const root = projectId ? await getWorkspaceRoot(projectId) : getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, isRepo: false, error: '未选择项目工作区' };
  }
  return getGitStatus(root);
});

ipcMain.handle('kyrozen:commit-and-push', async (_event, message: string) => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, error: '未选择项目工作区' };
  }
  return commitAndPush(root, githubAccessToken, message);
});

ipcMain.handle('kyrozen:create-github-repo', async (_event, owner: string, name: string, description?: string, isPrivate?: boolean) => {
  if (!githubAccessToken) {
    return { success: false, error: '未绑定 GitHub 账号' };
  }
  try {
    const resp = await fetch('https://api.github.com/user/repos', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${githubAccessToken}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name,
        description: description || '',
        private: isPrivate !== undefined ? isPrivate : false,
        auto_init: false,
        visibility: isPrivate !== false ? 'private' : 'public',
      }),
    });
    const repoData = await resp.json();
    if (resp.ok) {
      const cloneUrl = (repoData as any).clone_url || (repoData as any).ssh_url;
      // 3.5 #4: after creation set origin so the local repo can push.
      const root = getCurrentWorkspaceRoot();
      if (root && cloneUrl) {
        await initGitRepo(root, cloneUrl);
        const pushed = await commitAndPush(root, githubAccessToken, 'chore: publish initial Kyrozen project');
        if (!pushed.success) {
          return {
            success: false,
            failureKind: pushed.failureKind || 'push_failed',
            reason: pushed.reason || pushed.error || '仓库已创建，但首次推送失败',
            recovery: pushed.recovery || '检查网络与 GitHub 权限后重试推送。',
            url: (repoData as any).html_url,
            cloneUrl,
          };
        }
      }
      logInfo(`Created GitHub repo ${name}: ${cloneUrl}`);
      return { success: true, url: (repoData as any).html_url, cloneUrl, owner: owner || (repoData as any).owner?.login };
    }
    // Classify the failure (e.g. repo name already exists) and surface a reason + recovery.
    const classified = classifyCreateRepoError(resp.status, repoData);
    return {
      success: false,
      failureKind: classified.kind,
      reason: classified.reason,
      recovery: classified.recovery,
      error: (repoData as any).message || `HTTP ${resp.status}`,
    };
  } catch (err: any) {
    const classified = classifyCreateRepoError(0, null);
    return { success: false, failureKind: classified.kind, reason: classified.reason, recovery: classified.recovery, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:get-git-commits', async (_event, projectId?: string) => {
  const root = projectId ? await getWorkspaceRoot(projectId) : getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, commits: [], remoteUrl: null, error: '未选择项目工作区' };
  }
  return getGitCommits(root);
});

ipcMain.handle('kyrozen:set-auto-commit', async (_event, enabled: boolean) => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, error: '未选择项目工作区' };
  }
  return setAutoCommit(root, enabled);
});

ipcMain.handle('kyrozen:get-auto-commit', async () => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { enabled: false };
  }
  return getAutoCommit(root);
});

ipcMain.handle('kyrozen:ensure-project-venv', async () => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, pythonPath: null, error: '未选择项目工作区' };
  }
  const basePython = pythonRuntimePath || (await getCachedPythonRuntime()) || 'python3';
  const result = await ensureProjectVenv(root, basePython, (msg) => sendTaskActivity({ description: msg }));
  if (result.error) {
    return { success: false, pythonPath: result.pythonPath, error: result.error };
  }
  return { success: true, pythonPath: result.pythonPath, created: result.created };
});

ipcMain.handle('kyrozen:install-project-deps', async (_event, packages?: string[]) => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { success: false, installed: [], error: '未选择项目工作区' };
  }
  return installProjectDependencies(root, packages, (msg) => sendTaskActivity({ description: msg }));
});

ipcMain.handle('kyrozen:get-project-venv', async () => {
  const root = getCurrentWorkspaceRoot();
  if (!root) {
    return { ready: false, pythonPath: null };
  }
  return getProjectVenv(root);
});

ipcMain.handle('kyrozen:get-onboarding-status', async () => {
  onboardingConfig = await loadOnboardingConfig();
  return { ...onboardingConfig };
});

ipcMain.handle('kyrozen:get-onboarding-language', async () => {
  onboardingConfig = await loadOnboardingConfig();
  return { language: onboardingConfig.language };
});

ipcMain.handle('kyrozen:save-onboarding-language', async (_event, language: 'zh' | 'en') => {
  await saveOnboardingConfig({ language });
  return { language };
});

ipcMain.handle('kyrozen:complete-onboarding', async (_event, language?: 'zh' | 'en') => {
  const patch: Partial<OnboardingConfig> = { completed: true, completedAt: new Date().toISOString() };
  if (language) patch.language = language;
  await saveOnboardingConfig(patch);
  return { ...onboardingConfig };
});

ipcMain.handle('kyrozen:logout', async () => {
  await clearCredentials();
  disconnectWebSocket();
  stopPythonAgent();
  serverUrl = normalizeServerUrl(resolveDefaultServerUrl());
  setUpdateApiBaseUrl(serverUrl);
  wsUrl = getWebSocketUrlFromHttp(serverUrl);
  currentProjectId = null;
  accessToken = null;
  githubAccessToken = null;
  githubTokenScope = null;
  workspaceMap = {};
  mainWindow?.webContents.send('kyrozen:session-ended');
  return { success: true };
});

ipcMain.handle('kyrozen:check-python-runtime', async () => {
  try {
    const cached = await getCachedPythonRuntime();
    if (cached) {
      return { ready: true, path: cached };
    }
    return { ready: false, path: null };
  } catch (err: any) {
    return { ready: false, path: null, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:ensure-python-runtime', async () => {
  try {
    const repoRoot = getRepoRoot();
    const pythonPath = await ensurePythonRuntime(repoRoot, (msg) => {
      sendOnboardingProgress('python', msg);
    });
    if (pythonPath) {
      pythonRuntimePath = pythonPath;
      pythonRuntimeReady = true;
      setPythonExe(pythonPath);
    }
    return { success: true, path: pythonPath };
  } catch (err: any) {
    logError(`Python runtime setup failed: ${err.message || err}`);
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:pick-onboarding-workspace', async () => {
  const defaultPath = path.join(app.getPath('home'), 'KyrozenProjects');
  const result = await dialog.showOpenDialog(mainWindow!, {
    title: '选择本地项目目录',
    defaultPath,
    properties: ['openDirectory', 'createDirectory', 'promptToCreate'],
    buttonLabel: '选择此文件夹',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { workspaceRoot: null };
  }
  const selected = result.filePaths[0];
  await fs.mkdir(selected, { recursive: true });
  return { workspaceRoot: selected };
});

ipcMain.handle('kyrozen:import-local-project', async () => {
  const defaultPath = app.getPath('home');
  const result = await dialog.showOpenDialog(mainWindow!, {
    title: '导入已有本地目录作为 Kyrozen 项目',
    defaultPath,
    properties: ['openDirectory', 'promptToCreate'],
    buttonLabel: '导入此文件夹',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  const selected = result.filePaths[0];
  await ensureWorkspaceStructure(selected);
  const dirName = path.basename(selected);
  const projectId = `local_${dirName}_${Date.now()}`;
  workspaceMap[projectId] = selected;
  await saveWorkspaceMap();
  logInfo(`Imported local project ${projectId} at ${selected}`);
  return {
    projectId,
    name: dirName,
    workspaceRoot: selected,
    current_stage: '本地导入',
    localOnly: true,
  };
});

ipcMain.on('kyzen:software-feature', (_event, params: unknown) => {
  logInfo('Forwarding software_feature request to Python Agent');
  sendToPythonAgent({ jsonrpc: '2.0', method: 'software_feature', params });
});

// Feature 3.4: attachments / status / operation logs / confirmations.
ipcMain.on('kyzen:interaction', (_event, params: unknown) => {
  logInfo('Forwarding interaction request to Python Agent');
  sendToPythonAgent({ jsonrpc: '2.0', method: 'interaction', params });
});

ipcMain.on('kyrozen:request-initial-token', () => {
  const url = getProtocolUrl();
  logInfo(`Renderer requested initial token, protocolUrl=${url ? redactProtocolUrl(url) : 'none'}`);
  if (url) {
    mainWindow?.webContents.send('kyrozen:protocol-url', url);
  } else if (currentWsToken) {
    mainWindow?.webContents.send('kyrozen:session-resumed', currentWsToken, serverUrl);
  }
  // Send the current connection state in case the renderer missed earlier events
  // (for example, when resuming a saved session before the window finished loading).
  mainWindow?.webContents.send('kyrozen:connection-change', currentConnectionState, currentConnectionMessage);
  if (pythonAgentReady) {
    mainWindow?.webContents.send('kyzon:agent-ready', { status: 'ready', version: app.getVersion(), mode: 'local' });
  }
});

ipcMain.handle('kyrozen:get-initial-session', () => ({
  wsToken: currentWsToken,
  serverUrl,
  currentProjectId,
  connection: currentConnectionState,
  message: currentConnectionMessage,
}));

ipcMain.handle('kyrozen:get-user-profile', async () => {
  const claims = decodeAccessTokenClaims();
  const metadata = claims.user_metadata || {};
  let username = String(metadata.github_username || metadata.user_name || metadata.preferred_username || '');
  let avatarUrl = String(metadata.avatar_url || metadata.picture || '');
  let githubName = '';
  if (githubAccessToken) {
    try {
      const response = await fetch('https://api.github.com/user', {
        headers: { Authorization: `Bearer ${githubAccessToken}`, Accept: 'application/vnd.github+json' },
      });
      if (response.ok) {
        const githubUser = await response.json() as Record<string, unknown>;
        username = String(githubUser.login || username);
        avatarUrl = String(githubUser.avatar_url || avatarUrl);
        githubName = String(githubUser.name || '');
      }
    } catch (err: any) {
      logWarn(`Failed to fetch GitHub avatar: ${err.message || err}`);
    }
  }
  return {
    name: String(githubName || metadata.name || metadata.full_name || username || claims.email || 'Kyrozen 用户'),
    email: String(claims.email || ''),
    githubUsername: username,
    avatarUrl: avatarUrl || (username ? `https://avatars.githubusercontent.com/${username}` : ''),
  };
});

ipcMain.handle('kyrozen:send-chat', async (_event, message: string) => {
  if (!accessToken) return { success: false, error: '未登录' };
  if (!currentProjectId) return { success: false, error: '请先选择项目' };
  if (wsClient?.readyState !== WebSocket.OPEN) return { success: false, error: '桌面客户端尚未连接云端' };
  try {
    const projectState = await apiGet(`/api/projects/${currentProjectId}/state`);
    const modeByStage: Record<string, string> = {
      problem_discovery: 'discovery',
      market_research: 'market_research',
      product_definition: 'planning',
      solution_design: 'planning',
      development: 'development',
      testing: 'testing',
      iteration: 'learning',
    };
    const mode = modeByStage[String(projectState.stage || '')] || 'discovery';
    // P0-04: 开发阶段注入本地 PRD / TECH_DESIGN 上下文，Agent 不必依赖 Supabase artifacts。
    let enrichedMessage = message;
    if (mode === 'development') {
      try {
        const root = await getWorkspaceRoot(currentProjectId);
        if (root) {
          const parts: string[] = [];
          for (const doc of ['docs/PRD.md', 'docs/TECH_DESIGN.md']) {
            const docPath = path.join(root, doc);
            try { const content = await fs.readFile(docPath, 'utf-8'); if (content.trim()) parts.push(content); } catch {}
          }
          if (parts.length > 0) {
            enrichedMessage = `[Project Documents from workspace]\n\n${parts.join('\n\n---\n\n')}\n\n[End of project documents]\n\n${message}`;
          }
        }
      } catch { /* best-effort */ }
    }
    sendTaskActivity({ description: '正在理解你的需求' });
    const task = await apiPost('/api/chat', {
      message: enrichedMessage,
      project_id: currentProjectId,
      mode,
      stream: false,
    }, true);
    if (!task.dispatched_to_desktop && task.content) {
      const operations = Array.isArray(task.steps)
        ? task.steps.map((step: any) => ({
            description: String(step.description || '处理任务'),
            status: String(step.status || 'completed'),
            timestamp: String(step.completed_at || step.started_at || new Date().toISOString()),
          }))
        : [];
      sendTaskActivity({ task_id: String(task.task_id || ''), description: '回复已完成', status: 'completed' });
      return {
        success: true,
        taskId: task.task_id,
        dispatched: false,
        content: String(task.content),
        operations,
      };
    }
    if (task.dispatched_to_desktop && task.task_id) {
      // The cloud accepted the task and will push assign_task over WS. If
      // that push never arrives, fail fast instead of spinning forever.
      startDispatchWatchdog(String(task.task_id));
    }
    return { success: true, taskId: task.task_id, dispatched: !!task.dispatched_to_desktop };
  } catch (err: any) {
    logError(`Failed to submit desktop chat: ${err.message || err}`);
    return { success: false, error: err.message || '发送失败' };
  }
});

// P0-14: 从后端加载聊天历史，重启后恢复对话。
ipcMain.handle('kyrozen:load-chat-messages', async (_event, projectId: string) => {
  if (!accessToken) return { success: false, messages: [], error: '未登录' };
  try {
    const data = await apiGet(`/api/projects/${encodeURIComponent(projectId)}/chat`);
    const messages = Array.isArray(data) ? data : (Array.isArray(data?.messages) ? data.messages : []);
    return { success: true, messages };
  } catch (err: any) {
    logWarn(`Failed to load chat messages for ${projectId}: ${err.message || err}`);
    return { success: false, messages: [], error: err.message || String(err) };
  }
});

ipcMain.on('kyrozen:cancel-task', () => {
  if (currentTaskId && currentTaskRunning) {
    // Record the cancellation BEFORE the agent replies so a racing
    // `completed` result for this task is never appended to the chat.
    cancelledTaskIds.add(currentTaskId);
    sendTaskActivity({ task_id: currentTaskId, description: '正在停止任务…' });
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'cancel_task',
      params: { task_id: currentTaskId },
    });
  }
});

// Stage gate (feature 3.2): forward the renderer's gate action to the Python
// Agent. The agent re-scans deliverables, applies the transition and pushes a
// fresh `stage_updated` event back to the UI.
ipcMain.handle('kyrozen:stage-action', async (_event, action: string, stage: string, riskDetails?: Record<string, string>) => {
  const projectId = currentProjectId || '';
  const workspaceRoot = await chooseWorkspaceRoot(projectId);
  sendToPythonAgent({
    jsonrpc: '2.0',
    id: Date.now(),
    method: 'stage_action',
    params: { action, workspace_root: workspaceRoot, project_id: projectId, stage, risk_details: riskDetails || {} },
  });
  return { ok: true };
});

/** Establish or re-establish the WebSocket connection to the Kyrozen cloud. */
function connectWebSocket(token: string) {
  disconnectWebSocket();
  updateConnection('connecting', '正在连接云端...');
  logInfo(`Connecting WebSocket to ${wsUrl}`);

  try {
    wsClient = new WebSocket(wsUrl);

    wsClient.on('open', async () => {
      logInfo('WebSocket opened, sending auth');
      wsClient?.send(
        JSON.stringify({
          type: 'auth',
          token,
          device_name: os.hostname(),
          client_version: app.getVersion(),
          platform: process.platform,
          current_project_id: currentProjectId,
        })
      );
      updateConnection('connecting', '正在验证云端会话...');
      pythonAgentRestartCount = 0;
      startHeartbeat();
      flushPendingCloudMessages();
      // Ask the cloud for any tasks that were assigned while the client was offline.
      wsClient?.send(
        JSON.stringify({
          type: 'request_pending_tasks',
          current_project_id: currentProjectId,
        })
      );
      if (currentTaskId && currentTaskRunning) {
        sendToCloud({
          type: 'task_step',
          task_id: currentTaskId,
          step: {
            description: 'WebSocket 已重连，继续执行任务',
            status: 'running',
            metadata: { action: 'reconnected_during_task' },
          },
        });
      }
      await startPythonAgent();
    });

    wsClient.on('message', async (data) => {
      try {
        const message = JSON.parse(data.toString());
        handleServerMessage(message);
      } catch {
        // ignore non-JSON messages
      }
    });

    wsClient.on('error', (err) => {
      logError(`WebSocket error: ${err.message}`);
      updateConnection('error', `WebSocket 错误: ${err.message}`);
    });

    wsClient.on('close', (code: number, reason: Buffer) => {
      const closeReason = reason.toString();
      logWarn(`WebSocket closed: code=${code}, reason=${closeReason || 'none'}`);
      if (code === 1008 && /invalid websocket token/i.test(closeReason)) {
        updateConnection('connecting', '会话已更新，正在安全重连...');
        void reconnectWithFreshWebSocketToken();
        return;
      }
      updateConnection('disconnected', '连接已断开，5 秒后重连');
      scheduleReconnect(token);
    });
  } catch (err: any) {
    logError(`WebSocket connection exception: ${err.message || err}`);
    updateConnection('error', err.message || '连接失败');
    scheduleReconnect(token);
  }
}

function disconnectWebSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  stopHeartbeat();
  if (wsClient) {
    wsClient.removeAllListeners();
    wsClient.close();
    wsClient = null;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (wsClient?.readyState === WebSocket.OPEN) {
      wsClient.send(
        JSON.stringify({
          type: 'heartbeat',
          current_project_id: currentProjectId,
        })
      );
    }
  }, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function getTaskTimeoutForPayload(payload: Record<string, unknown>): number {
  const params = (payload.params as Record<string, unknown>) || {};
  const mode = String(params.mode || '').toLowerCase();
  const message = String(params.message || '').toLowerCase();
  if (mode === 'hardware' || /\b(arduino|esp32|platformio|hardware|pio)\b/.test(message)) {
    return HARDWARE_TIMEOUT_MS;
  }
  if (/\b(install|npm|yarn|pnpm|pip|依赖)\b/.test(message)) {
    return DEPENDENCY_TIMEOUT_MS;
  }
  if (/\b(model|llm|chat|生成|思考|推理)\b/.test(message)) {
    return MODEL_TIMEOUT_MS;
  }
  return TASK_TIMEOUT_MS;
}

async function restartPythonAgentAndRetryTask() {
  logInfo(`Retrying task ${currentTaskId} (attempt ${taskRetryCount}/${MAX_TASK_RETRIES})`);
  stopPythonAgent();
  clearTaskTimeout();
  await startPythonAgent();
  if (lastTaskPayload && currentTaskId && currentTaskRunning) {
    startTaskTimeout(getTaskTimeoutForPayload(lastTaskPayload));
    sendToPythonAgent(lastTaskPayload);
    sendToCloud({
      type: 'task_step',
      task_id: currentTaskId,
      step: {
        description: `任务超时后自动重做 (尝试 ${taskRetryCount}/${MAX_TASK_RETRIES})`,
        status: 'running',
        metadata: { action: 'retry_after_timeout' },
      },
    });
  }
}

async function handleTaskTimeout() {
  if (!currentTaskId || !currentTaskRunning) return;
  logWarn(`Task ${currentTaskId} timed out`);
  sendToPythonAgent({
    jsonrpc: '2.0',
    method: 'cancel_task',
    params: { task_id: currentTaskId },
  });

  if (taskRetryCount < MAX_TASK_RETRIES) {
    taskRetryCount += 1;
    sendTaskActivity({ task_id: currentTaskId, description: '任务执行超时，正在重试' });
    await restartPythonAgentAndRetryTask();
    return;
  }

  currentTaskRunning = false;
  const previousTaskId = currentTaskId;
  taskRetryCount = 0;
  sendTaskActivity({ task_id: previousTaskId, description: '任务执行超时，已停止', status: 'failed' });
  sendToCloud({
    type: 'task_result',
    task_id: previousTaskId,
    status: 'failed',
    result: { error: 'Task timed out after retries' },
  });
  // Finalize the chat so the renderer never stays stuck on "正在理解你的需求".
  sendChatMessage({ role: 'error', content: '', error: '任务执行超时，请稍后重试或重启本地 Agent。', operations: [] });
}

function startTaskTimeout(timeoutMs = TASK_TIMEOUT_MS) {
  clearTaskTimeout();
  taskTimeoutTimer = setTimeout(() => {
    void handleTaskTimeout();
  }, timeoutMs);
}

function clearTaskTimeout() {
  if (taskTimeoutTimer) {
    clearTimeout(taskTimeoutTimer);
    taskTimeoutTimer = null;
  }
}

function scheduleReconnect(token: string) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket(token);
  }, 5000);
}

/** Route messages from the cloud to the local Python Agent or UI. */
async function processNextQueuedTask(): Promise<void> {
  if (pendingTasks.length === 0 || currentTaskRunning) return;
  const next = pendingTasks.shift();
  if (!next) return;
  logInfo(`Processing queued task ${next.task_id}`);
  await handleServerMessage(next);
}

async function handleServerMessage(message: Record<string, unknown>) {
  const type = message.type as string;
  logInfo(`Received server message: ${type}`);

  if (type === 'auth_success') {
    updateConnection('connected', '已连接云端');
  }

  if (type === 'assign_task') {
    clearDispatchWatchdog(String(message.task_id || ''));
    if (currentTaskRunning && String(message.task_id) === currentTaskId) {
      logInfo(`Ignoring duplicate assignment for active task ${currentTaskId}`);
      return;
    }
    if (currentTaskRunning) {
      pendingTasks.push(message);
      sendToCloud({
        type: 'task_queued',
        task_id: message.task_id,
        queue_length: pendingTasks.length,
      });
      sendTaskActivity({ task_id: String(message.task_id || ''), description: '任务已排队，等待执行' });
      return;
    }
    // The server can assign immediately after WebSocket auth, while the
    // bundled Python runtime is still being spawned. Do not mark the task as
    // running until an Agent exists; otherwise the payload is silently lost
    // and the UI remains stuck forever.
    if (!pythonAgent) {
      pendingTasks.unshift(message);
      sendTaskActivity({ task_id: String(message.task_id || ''), description: '正在准备本地 Agent' });
      void startPythonAgent();
      return;
    }
    currentTaskId = String(message.task_id);
    currentTaskRunning = true;
    taskRetryCount = 0;
    // Fetch stage and project info so the local AgentRouter can route by
    // project stage and project type, not just the dispatched mode.
    let projectStage = '';
    let projectType = '';
    try {
      const state = await apiGet(`/api/projects/${String(message.project_id || currentProjectId)}/state`);
      projectStage = String(state?.stage || '');
    } catch {
      // Best effort: routing falls back to the dispatched mode.
    }
    try {
      const project = await apiGet(`/api/projects/${String(message.project_id || currentProjectId)}`);
      const haystack = `${String(project?.name || '')} ${String(project?.description || '')} ${String(project?.goal || '')}`;
      if (/arduino|esp32|esp8266|stm32|raspberry|单片机|开发板|固件|电路|传感器|pcb|硬件/i.test(haystack)) {
        projectType = 'hardware';
      } else {
        projectType = 'software';
      }
    } catch {
      // Best effort: leave project type empty.
    }
    const payload = {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'run_task',
      params: {
        task_id: message.task_id,
        project_id: message.project_id,
        message: message.message,
        mode: message.mode,
        stage: projectStage,
        project_type: projectType,
        workspace_root: await chooseWorkspaceRoot(String(message.project_id || currentProjectId)),
      },
    };
    lastTaskPayload = payload;
    startTaskTimeout(getTaskTimeoutForPayload(payload));
    sendToPythonAgent(payload);
    wsClient?.send(
      JSON.stringify({
        type: 'task_accepted',
        task_id: message.task_id,
      })
    );
  }

  if (type === 'model_stream_chunk' || type === 'model_error') {
    sendToPythonAgent({ jsonrpc: '2.0', method: 'cloud_model_response', params: message });
  }

  if (type === 'cleanup_account') {
    const userId = String(message.user_id || '');
    logWarn(`Received account cleanup instruction for user ${userId}`);
    await handleAccountCleanup(userId);
  }

  if (type === 'connection_resumed') {
    if (currentTaskId && currentTaskRunning) {
      sendToCloud({
        type: 'task_step',
        task_id: currentTaskId,
        step: {
          description: 'WebSocket 重连成功，任务继续执行中',
          status: 'running',
          metadata: { action: 'connection_resumed' },
        },
      });
    }
  }
}

async function handleAccountCleanup(userId: string): Promise<void> {
  if (!userId) return;
  sendTaskActivity({ description: '正在清理本地项目数据' });
  try {
    for (const [projectId, root] of Object.entries(workspaceMap)) {
      try {
        await fs.rm(root, { recursive: true, force: true });
        logInfo(`Cleaned up workspace for project ${projectId}`);
      } catch (err: any) {
        logError(`Failed to cleanup workspace ${root}: ${err.message || err}`);
      }
    }
    workspaceMap = {};
    await saveWorkspaceMap();
    await clearCredentials();
    sendTaskActivity({ description: '本地项目数据已清理', status: 'completed' });
    showNotification('Kyrozen', '账户已删除，本地数据已清理');
    setTimeout(() => {
      isQuitting = true;
      app.quit();
    }, 3000);
  } catch (err: any) {
    logError(`Account cleanup failed: ${err.message || err}`);
    sendTaskActivity({ description: '本地项目数据清理失败', status: 'failed' });
  }
}

async function chooseWorkspaceRoot(projectId: string | null): Promise<string> {
  if (!projectId) return path.join(app.getPath('home'), 'KyrozenProjects');
  const root = await getWorkspaceRoot(projectId);
  if (root) return root;
  // Fallback if user cancels the picker.
  const fallback = path.join(app.getPath('home'), 'KyrozenProjects', projectId);
  await fs.mkdir(fallback, { recursive: true });
  return fallback;
}

function getRepoRoot(): string {
  if (app.isPackaged) return process.resourcesPath;
  // main.js is inside dist-electron/main/, which is under desktop/; repo root is one level above desktop.
  return path.resolve(currentDir, '../../../');
}

function getPythonAgentScript(): string {
  if (process.env.KYROZEN_AGENT_SCRIPT) return process.env.KYROZEN_AGENT_SCRIPT;
  if (app.isPackaged) return path.join(process.resourcesPath, 'python_agent', 'main.py');
  return path.join(currentDir, '../../python_agent/main.py');
}

/** Spawn the local Python Agent process and wire stdio JSON-RPC to the UI/cloud. */
function startPythonAgent(): Promise<void> {
  // WebSocket open/reconnect, protocol login, and retry paths can all request
  // an Agent at the same time. Serialize startup so only one child owns the
  // stdio channel; concurrent children otherwise leave tasks hanging forever.
  if (pythonAgent) return Promise.resolve();
  if (pythonAgentStartPromise) return pythonAgentStartPromise;
  pythonAgentStartPromise = startPythonAgentInternal().finally(() => {
    pythonAgentStartPromise = null;
  });
  return pythonAgentStartPromise;
}

async function startPythonAgentInternal() {
  logInfo('Starting Python Agent');
  stopPythonAgent();

  let pythonPath = process.env.KYROZEN_PYTHON_PATH;
  if (!pythonPath) {
    if (!pythonRuntimeReady) {
      logInfo('Preparing local Python runtime');
      try {
        pythonRuntimePath = await ensurePythonRuntime(getRepoRoot(), (msg) => {
          logInfo(msg);
        });
        pythonRuntimeReady = true;
        if (pythonRuntimePath) {
          logInfo('Bundled Python runtime ready');
        }
      } catch (err: any) {
        logWarn(`Bundled Python unavailable; falling back to system Python: ${err.message || err}`);
        pythonRuntimePath = null;
        pythonRuntimeReady = true;
      }
    }
    pythonPath = pythonRuntimePath || 'python3';
  }

  const extraEnv: Record<string, string> = {
    KYROZEN_WS_URL: wsUrl,
    KYROZEN_DESKTOP_MODE: '1',
    KYROZEN_RESOURCE_ROOT: getRepoRoot(),
    KYROZEN_LOG_DIR: path.join(app.getPath('userData'), 'logs'),
    KYROZEN_TASK_STORE_PATH: path.join(app.getPath('userData'), 'kyrozen_tasks.json'),
  };

  if (pythonRuntimePath) {
    setPythonExe(pythonRuntimePath);
    // Start daily auto-update checks for hardware tools once a Python runtime is available.
    startHardwareToolchainAutoUpdate((msg) => logInfo(msg));
    // Resolve hardware toolchain paths before spawning the Agent so that the
    // bundled tools are discoverable by HardwareBridge via environment vars.
    try {
      const arduino = await ensureArduinoCLI((msg) => logInfo(msg));
      if (arduino.path) {
        extraEnv.KYROZEN_ARDUINO_CLI_PATH = arduino.path;
      }
    } catch (err: any) {
      logWarn(`Arduino CLI setup failed: ${err.message || err}`);
    }
    try {
      // P0-R11: the bundled PlatformIO is intentionally not on PATH, so the
      // "not found, installing" message fires on every agent start even when it
      // is already installed (the pip install is then a no-op). Suppress that
      // specific noisy line from the main log; real install progress still logs.
      const pio = await ensurePlatformIO((msg) => {
        if (!/not found|installing/i.test(msg)) logInfo(msg);
      });
      if (pio.path) {
        extraEnv.KYROZEN_PIO_PATH = pio.path;
      }
    } catch (err: any) {
      logWarn(`PlatformIO setup failed: ${err.message || err}`);
    }
    mainWindow?.webContents.send('kyrozen:hardware-tool-status', getToolStatus());
  }

  const agentScript = getPythonAgentScript();
  logInfo(`Spawning Python Agent: ${pythonPath} ${agentScript}`);

  pythonAgent = spawn(pythonPath, [agentScript], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      ...extraEnv,
    },
  });
  pythonAgentReady = false;

  // A JSON-RPC line can span multiple pipe chunks. Decode UTF-8 as a stream
  // and retain the incomplete tail instead of attempting to parse each chunk.
  pythonAgentStdoutBuffer = '';
  pythonAgent.stdout.setEncoding('utf8');
  pythonAgent.stdout.on('data', (data: string) => {
    pythonAgentStdoutBuffer += data;
    const lines = pythonAgentStdoutBuffer.split('\n');
    pythonAgentStdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (line.trim()) handlePythonAgentLine(line);
    }
  });

  pythonAgent.stderr.on('data', (data: Buffer) => {
    logWarn(`Python Agent stderr: ${data.toString().trim()}`);
  });

  pythonAgent.on('error', (err) => {
    logError(`Python Agent spawn error: ${err.message}`);
    sendTaskActivity({ description: '本地 Agent 启动失败', status: 'failed' });
  });

  pythonAgent.on('exit', (code) => {
    logWarn(`Python Agent exited with code ${code ?? 'unknown'}`);
    sendTaskActivity({ description: '本地 Agent 已停止', status: code === 0 ? 'completed' : 'failed' });
    // If a chat task was still running when the Agent died, finalize it so the
    // renderer does not stay stuck on "正在理解你的需求" forever.
    if (currentTaskRunning) {
      currentTaskRunning = false;
      clearTaskTimeout();
      const diedTaskId = currentTaskId;
      sendToCloud({
        type: 'task_result',
        task_id: diedTaskId,
        status: 'failed',
        result: { error: 'Local agent process exited unexpectedly' },
      });
      sendChatMessage({ role: 'error', content: '', error: '本地 Agent 已停止，请稍后重试。', operations: [] });
      if (diedTaskId) taskOperations.delete(String(diedTaskId));
    }
    // Tell the renderer the Agent is no longer available so it can stop any
    // infinite loading state and show a degraded/offline notice (P0-03/04/06).
    mainWindow?.webContents.send('kyzon:agent-ready', {
      status: 'down',
      code: code ?? null,
      retrying: !pythonAgentStopping && code !== 0,
    });
    pythonAgent = null;
    pythonAgentReady = false;
    if (!pythonAgentStopping && code !== 0) {
      if (pythonAgentRestartCount < PYTHON_AGENT_MAX_RESTARTS) {
        pythonAgentRestartCount += 1;
        const delay = Math.min(5000 * pythonAgentRestartCount, 30000);
        sendTaskActivity({ description: '本地 Agent 异常退出，正在重启' });
        setTimeout(() => {
          if (wsClient?.readyState === WebSocket.OPEN) {
            startPythonAgent();
          }
        }, delay);
      } else {
        sendTaskActivity({ description: '本地 Agent 无法启动，请检查运行环境', status: 'failed' });
        showNotification('Kyrozen', '本地 Agent 无法启动，请检查 Python 环境');
      }
    }
    pythonAgentStopping = false;
  });

  // A task may have arrived while the runtime/toolchain was starting. Flush
  // it only after the child process and its stdin handlers are ready.
  void processNextQueuedTask();
}

function stopPythonAgent() {
  if (pythonAgent) {
    pythonAgentStopping = true;
    pythonAgent.kill();
    pythonAgent = null;
    pythonAgentReady = false;
  }
  pythonAgentStdoutBuffer = '';
}

function sendToPythonAgent(payload: unknown) {
  if (!pythonAgent) return;
  pythonAgent.stdin.write(JSON.stringify(payload) + '\n');
}

function sendToCloud(payload: object) {
  const text = JSON.stringify(payload);
  if (wsClient?.readyState === WebSocket.OPEN) {
    wsClient.send(text);
  } else {
    pendingCloudMessages.push(text);
  }
}

function flushPendingCloudMessages() {
  if (!wsClient || wsClient.readyState !== WebSocket.OPEN) return;
  while (pendingCloudMessages.length > 0) {
    const message = pendingCloudMessages.shift();
    if (message) wsClient.send(message);
  }
}

/** Parse one JSON-RPC line from the Python Agent and dispatch it. */
function handlePythonAgentLine(line: string) {
  try {
    const message = JSON.parse(line);
    if (message.type === 'model_request') {
      logInfo(`Forwarding model request ${String(message.request_id || 'unknown')} to cloud`);
      sendToCloud(message);
    } else if (message.method === 'task_step') {
      const step = message.params.step || {};
      sendToCloud({ type: 'task_step', task_id: message.params.task_id, step });
      sendTaskActivity({
        task_id: String(message.params.task_id || currentTaskId || ''),
        description: String(step.description || '正在处理任务'),
        status: String(step.status || 'running'),
      });
    } else if (message.method === 'task_operation') {
      const taskId = String(message.params.task_id || currentTaskId || '');
      const operation = {
        description: String(message.params.description || '正在处理任务'),
        status: String(message.params.status || 'running'),
        timestamp: new Date().toISOString(),
      };
      const history = taskOperations.get(taskId) || [];
      history.push(operation);
      taskOperations.set(taskId, history.slice(-200));
      sendTaskActivity({ task_id: taskId, description: operation.description, status: operation.status });
    } else if (message.method === 'agent_routed') {
      const display = String(message.params?.agent_display_name || message.params?.agent_name || 'Agent');
      logInfo(`Task routed to ${String(message.params?.agent_name || '')} (mode=${String(message.params?.mode || '')})`);
      mainWindow?.webContents.send('kyrozen:agent-routed', message.params);
      sendTaskActivity({
        task_id: String(message.params?.task_id || currentTaskId || ''),
        description: `由${display}处理`,
        status: 'running',
      });
    } else if (message.method === 'agent_degraded') {
      logWarn(`Local agent degraded to read-only: ${String(message.params?.reason || '')}`);
      mainWindow?.webContents.send('kyrozen:agent-degraded', message.params);
      showNotification('Kyrozen', '本地 Agent 初始化失败，已降级为只读模式');
    } else if (message.method === 'ready') {
      // The bundled Python Agent finished booting (no import crash) and is
      // ready to accept requests. Surface this so the UI stops showing an
      // undefined loading state and can detect an Agent that later dies
      // (P0-03 / P0-04 / P0-06).
      logInfo(`Python Agent ready: ${String(message.params?.version || 'unknown')}`);
      pythonAgentReady = true;
      mainWindow?.webContents.send('kyzon:agent-ready', {
        status: 'ready',
        version: String(message.params?.version || ''),
        mode: String(message.params?.mode || ''),
      });
    } else if (message.method === 'stage_updated') {
      mainWindow?.webContents.send('kyrozen:stage-updated', message.params);
      const stageProjectId = String(message.params?.project_id || currentProjectId || '');
      if (stageProjectId && accessToken) {
        void apiPut(`/api/projects/${encodeURIComponent(stageProjectId)}`, {
          current_stage: String(message.params?.stage || 'problem_discovery'),
          progress: Number(message.params?.progress || 0),
        }).then(() => {
          // P0-06: only re-dispatch if the user is still on the same project.
          if (currentProjectId && currentProjectId !== stageProjectId) return;
          mainWindow?.webContents.send('kyrozen:stage-updated', message.params);
        }).catch((err: any) => logWarn(`Failed to sync stage to cloud: ${err.message || err}`));
      }
    } else if (message.method === 'software_feature') {
      // 3.3 real software generation / run / repair results for the UI panel.
      mainWindow?.webContents.send('kyzen:software-feature', message.params);
    } else if (message.method === 'status_updated') {
      // 3.4 status bar: only the six user-facing states reach the renderer.
      mainWindow?.webContents.send('kyzen:status-updated', message.params);
    } else if (message.method === 'interaction') {
      // 3.4 attachments / operation log / confirmation results for the UI panel.
      mainWindow?.webContents.send('kyzen:interaction', message.params);
    } else if (message.method === 'request_confirmation') {
      showConfirmationDialog(message.params);
      showNotification('Kyrozen', `请求确认：${message.params.tool}.${message.params.action}`);
    } else if (message.method === 'model_request') {
      sendToCloud(message.params);
    } else if (message.method === 'hardware_tool_request') {
      const command = String(message.params?.command || '');
      const reqId = message.id;
      resolveHardwareCommand(command)
        .then((resolvedPath) => {
          sendToPythonAgent({
            jsonrpc: '2.0',
            id: reqId,
            result: { path: resolvedPath, command },
          });
        })
        .catch((err: any) => {
          sendToPythonAgent({
            jsonrpc: '2.0',
            id: reqId,
            error: { message: err.message || String(err), code: -32000 },
          });
        });
    } else if (message.method === 'open_preview') {
      const url = String(message.params.url || '');
      if (url) {
        // Prefer the inline preview panel; user can move it to a window from the UI.
        mainWindow?.webContents.send('kyrozen:open-preview-url', url);
        sendTaskActivity({ description: '已打开本地预览', status: 'completed' });
      }
    } else if (message.method === 'execution_plan') {
      sendExecutionPlan({
        task_id: String(message.params.task_id || currentTaskId || ''),
        steps: Array.isArray(message.params.steps) ? message.params.steps : [],
      });
    } else if (message.method === 'plan_updated') {
      // P0-R6: the agent saved/updated .kyrozen/PLAN.json. Forward the full
      // plan so the desktop renders it as the task panel (instead of guessing
      // bullet points out of model output).
      mainWindow?.webContents.send('kyrozen:plan-updated', {
        task_id: String(message.params.task_id || currentTaskId || ''),
        plan: message.params.plan || {},
        source: message.params.source || 'unknown',
      });
    } else if (message.method === 'task_result') {
      currentTaskRunning = false;
      taskRetryCount = 0;
      clearTaskTimeout();
      void processNextQueuedTask();
      const resultTaskId = String(message.params.task_id || currentTaskId || '');
      // Cancel race fix: if the user pressed stop, a late `completed` result
      // must be treated as cancelled and never appended to the chat.
      const wasCancelled = cancelledTaskIds.delete(resultTaskId);
      const status = wasCancelled && message.params.status === 'completed'
        ? 'cancelled'
        : message.params.status;
      sendToCloud({
        type: 'task_result',
        task_id: message.params.task_id,
        status,
        result: message.params.result,
        steps: message.params.steps,
      });
      const answer = message.params.result?.answer
        || message.params.result?.error
        || (status === 'failed' ? 'AI 服务暂时不可用，请稍后重试。' : '任务完成');
      const operations = taskOperations.get(String(message.params.task_id || currentTaskId || '')) || [];
      if (status === 'failed') {
        sendTaskActivity({
          task_id: String(message.params.task_id || currentTaskId || ''),
          description: '处理失败，请查看提示后重试',
          status: 'failed',
        });
        sendChatMessage({ role: 'error', content: '', error: answer, operations });
      } else if (status === 'cancelled') {
        sendTaskActivity({
          task_id: String(message.params.task_id || currentTaskId || ''),
          description: '任务已取消',
          status: 'failed',
        });
      } else {
        sendTaskActivity({
          task_id: String(message.params.task_id || currentTaskId || ''),
          description: '回复已完成',
          status: 'completed',
        });
        sendChatMessage({ role: 'assistant', content: answer, operations });
      }
      taskOperations.delete(String(message.params.task_id || currentTaskId || ''));
      if (status === 'failed') {
        showNotification('Kyrozen', '任务执行失败');
      } else if (status === 'cancelled') {
        showNotification('Kyrozen', '任务已取消');
      } else if (status === 'completed') {
        showNotification('Kyrozen', '任务已完成');
      }
    }
  } catch {
    logWarn(`Ignoring non-JSON Agent output: ${line.slice(0, 300)}`);
  }
}

function openPreviewWindow(url: string) {
  if (previewWindow) {
    previewWindow.loadURL(url);
    previewWindow.focus();
    return;
  }

  previewWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 600,
    minHeight: 400,
    title: 'Kyrozen 预览',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  previewWindow.loadURL(url);

  previewWindow.on('closed', () => {
    previewWindow = null;
  });
}

ipcMain.handle('kyrozen:open-preview', async (_event, url: string, mode: 'embedded' | 'window' | 'external') => {
  if (!/^https?:\/\/localhost(:\d+)(\/.*)?$/.test(url)) {
    return { success: false, error: '只允许 localhost 预览链接' };
  }
  if (mode === 'external') {
    await shell.openExternal(url);
    return { success: true };
  }
  if (mode === 'window') {
    openPreviewWindow(url);
    return { success: true };
  }
  // embedded: notify renderer to show the inline preview panel.
  mainWindow?.webContents.send('kyrozen:open-preview-url', url);
  return { success: true };
});

const DANGEROUS_PATTERNS = [
  /rm\s+-rf\s+\//,
  /sudo\b/,
  /\bssh\b/,
  />\s*\/dev\/[sh]d[a-z]/,
  /mkfs\.\w+/,
  /dd\s+if=/,
  /:\(\)\{\s*:\|:\|/,
  /curl\s+.*\|\s*(bash|sh|zsh)\b/,
  /wget\s+.*\|\s*(bash|sh|zsh)\b/,
];

// Static list of known malicious or compromised packages for MVP.
// In production this should be replaced with a real-time security feed.
const KNOWN_MALICIOUS_PACKAGES = new Set([
  'event-stream',
  'flatmap-stream',
  'node-ipc',
  'colors',
  'faker',
  'rc',
  'left-pad',
  'ua-parser-js',
  'coa',
]);

function isDangerousCommand(command: string): boolean {
  return DANGEROUS_PATTERNS.some((pattern) => pattern.test(command));
}

function findMaliciousPackage(command: string): string | null {
  const packages = extractPackages(command);
  for (const pkg of packages) {
    const normalized = pkg.toLowerCase().replace(/^@[^/]+\//, '');
    if (KNOWN_MALICIOUS_PACKAGES.has(normalized)) {
      return pkg;
    }
  }
  return null;
}

function extractPackages(command: string): string[] {
  const installMatch = command.match(/\b(?:npm|yarn|pnpm)\s+(?:install|add)\s+(.+)/i);
  if (installMatch) {
    return installMatch[1]
      .split(/\s+/)
      .filter((arg) => arg && !arg.startsWith('-'));
  }
  const pipMatch = command.match(/\bpip\s+(?:install)\s+(.+)/i);
  if (pipMatch) {
    return pipMatch[1]
      .split(/\s+/)
      .filter((arg) => arg && !arg.startsWith('-'));
  }
  return [];
}

function buildConfirmationDetail(params: Record<string, unknown>): string {
  const parameters = (params.parameters as Record<string, unknown>) || {};
  const command = String(parameters.command || '');
  const filePath = String(parameters.path || parameters.file_path || '');
  let detail = `参数：${JSON.stringify(parameters, null, 2)}\n原因：${params.reason || '无'}`;

  if (String(params.tool) === 'terminal' && String(params.action) === 'execute' && command) {
    const packages = extractPackages(command);
    if (packages.length > 0) {
      detail += `\n\n将安装以下依赖，请确认来源可信：\n${packages.map((p) => `- ${p}`).join('\n')}`;
    }
  }

  if (String(params.tool) === 'file_write' && /(^|\/)\.env$/.test(filePath)) {
    detail += '\n\n注意：写入 .env 会包含敏感信息。建议生成 .env.example，让用户手动复制为 .env 并填入真实值。';
  }
  return detail;
}

async function showConfirmationDialog(params: Record<string, unknown>) {
  const command = String((params.parameters as Record<string, unknown>)?.command || '');
  if (String(params.tool) === 'terminal' && String(params.action) === 'execute' && isDangerousCommand(command)) {
    const reason = '检测到高危命令模式，已被客户端自动拒绝。';
    logError(`Rejected dangerous command: ${command}`);
    await logAuditEvent({
      taskId: String(params.task_id || ''),
      tool: String(params.tool || ''),
      action: String(params.action || ''),
      parameters: (params.parameters as Record<string, unknown>) || {},
      confirmed: false,
      fullTrust: fullTrustMode,
    });
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'confirmation_response',
      params: {
        confirmation_id: params.confirmation_id,
        confirmed: false,
        trust_for_session: false,
        task_id: params.task_id,
        error: reason,
      },
    });
    sendTaskActivity({ description: reason, status: 'failed' });
    return;
  }

  const maliciousPackage = String(params.tool) === 'terminal' && String(params.action) === 'execute' ? findMaliciousPackage(command) : null;
  if (maliciousPackage) {
    const reason = `检测到已知恶意或风险依赖包 ${maliciousPackage}，安装已被阻断。`;
    logError(`Blocked malicious package installation: ${maliciousPackage}`);
    await logAuditEvent({
      taskId: String(params.task_id || ''),
      tool: String(params.tool || ''),
      action: String(params.action || ''),
      parameters: (params.parameters as Record<string, unknown>) || {},
      confirmed: false,
      fullTrust: fullTrustMode,
    });
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'confirmation_response',
      params: {
        confirmation_id: params.confirmation_id,
        confirmed: false,
        trust_for_session: false,
        task_id: params.task_id,
        error: reason,
      },
    });
    sendTaskActivity({ description: reason, status: 'failed' });
    return;
  }

  const auditBase: AuditEvent = {
    taskId: String(params.task_id || ''),
    tool: String(params.tool || ''),
    action: String(params.action || ''),
    parameters: (params.parameters as Record<string, unknown>) || {},
    confirmed: false,
    fullTrust: fullTrustMode,
  };

  const operationType = `${String(params.tool)}.${String(params.action)}`;
  // Full trust and an operation type trusted from an inline confirmation both
  // bypass further prompts for this desktop session.
  if (fullTrustMode || trustedOperationTypes.has(operationType)) {
    logWarn(`Auto-confirming ${params.tool}.${params.action} because full-trust mode is enabled`);
    await logAuditEvent({ ...auditBase, confirmed: true, fullTrust: fullTrustMode });
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'confirmation_response',
      params: {
        confirmation_id: params.confirmation_id,
        confirmed: true,
        trust_for_session: fullTrustMode || trustedOperationTypes.has(operationType),
        task_id: params.task_id,
      },
    });
    return;
  }

  const confirmationId = String(params.confirmation_id || '');
  pendingConfirmations.set(confirmationId, params);
  mainWindow?.webContents.send('kyrozen:confirmation-request', {
    confirmation_id: confirmationId,
    store_id: String((params as Record<string, unknown>).store_id || ''),
    task_id: String(params.task_id || ''),
    tool: String(params.tool || ''),
    action: String(params.action || ''),
    parameters: (params.parameters as Record<string, unknown>) || {},
    reason: String(params.reason || ''),
    detail: buildConfirmationDetail(params),
  });
}

ipcMain.handle(
  'kyrozen:respond-confirmation',
  async (_event, confirmationId: string, confirmed: boolean, trustForSession = false, storeId?: string | null) => {
    const params = pendingConfirmations.get(confirmationId);
    // For confirmations restored after a restart there is no live in-memory
    // entry, but the durable store still holds the pending card; forward it
    // when a store_id is supplied (requirement #5: do NOT auto-execute).
    if (!params && !storeId) return { success: false, error: '确认请求已失效' };
    if (params) pendingConfirmations.delete(confirmationId);
    const operationType = params ? `${String(params.tool)}.${String(params.action)}` : '';
    if (params && confirmed && trustForSession) trustedOperationTypes.add(operationType);
    if (params) {
      await logAuditEvent({
        taskId: String(params.task_id || ''),
        tool: String(params.tool || ''),
        action: String(params.action || ''),
        parameters: (params.parameters as Record<string, unknown>) || {},
        confirmed,
        fullTrust: fullTrustMode,
      });
    }
    const resolvedStoreId = storeId ?? (params ? String((params as Record<string, unknown>).store_id ?? '') : '');
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'confirmation_response',
      params: {
        confirmation_id: confirmationId,
        confirmed,
        trust_for_session: trustForSession,
        store_id: resolvedStoreId,
        task_id: params ? params.task_id : '',
      },
    });
    return { success: true };
  },
);

function sanitizeLogForUpload(log: string): string {
  return log
    .replace(/\b[A-Za-z0-9_\-]{32,}\b/g, '<TOKEN>')
    .replace(/ws_[A-Za-z0-9_\-]+/g, '<WS_TOKEN>')
    .replace(/\/Users\/[^/\s]+/g, '<HOME>')
    .replace(/\/home\/[^/\s]+/g, '<HOME>')
    .replace(/C:\\\\Users\\\\[^\\\\\s]+/g, '<HOME>')
    .replace(/eyJ[A-Za-z0-9_\-]*\.eyJ[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*/g, '<JWT>');
}

async function uploadErrorReport(errorSummary: string): Promise<void> {
  if (!accessToken) {
    sendTaskActivity({ description: '未登录，无法上传错误报告', status: 'failed' });
    return;
  }
  try {
    let logContent = '';
    try {
      logContent = await fs.readFile(LOG_FILE, 'utf-8');
    } catch {
      logContent = 'No log file available';
    }
    await apiPost(
      '/api/events',
      {
        event_type: 'desktop.error_report',
        project_id: currentProjectId,
        payload: {
          summary: errorSummary,
          log: sanitizeLogForUpload(logContent.slice(-50000)),
          version: app.getVersion(),
          platform: process.platform,
          arch: process.arch,
          source: 'desktop',
        },
        session_id: accessToken.slice(-16),
      },
      true,
    );
    sendTaskActivity({ description: '错误报告已上传', status: 'completed' });
  } catch (err: any) {
    logError(`Failed to upload error report: ${err.message || err}`);
    sendTaskActivity({ description: '错误报告上传失败', status: 'failed' });
  }
}

async function promptAndUploadErrorReport(errorSummary: string) {
  if (!mainWindow) {
    // Defer until the main window is available.
    setTimeout(() => void promptAndUploadErrorReport(errorSummary), 1000);
    return;
  }
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'error',
    buttons: ['上传脱敏错误报告', '取消'],
    defaultId: 0,
    cancelId: 1,
    title: 'Kyrozen 遇到错误',
    message: '客户端发生错误，是否上传脱敏日志帮助我们排查？',
    detail: sanitizeLogForUpload(errorSummary.slice(0, 500)),
  });
  if (result.response === 0) {
    await uploadErrorReport(errorSummary);
  }
}
