import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, safeStorage, shell, Tray } from 'electron';
import path from 'path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs/promises';
import { watch, FSWatcher } from 'fs';
import WebSocket from 'ws';
import {
  ensureArduinoCLI,
  ensurePlatformIO,
  installCommonCores,
  resolveHardwareCommand,
  setPythonExe,
} from './hardwareToolchain';
import { ensurePythonRuntime, getCachedPythonRuntime } from './pythonRuntime';
import { checkForUpdates, initAutoUpdater, setUpdateApiBaseUrl, stopUpdateChecks } from './updater';

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

let mainWindow: BrowserWindow | null = null;
let wsClient: WebSocket | null = null;
let pythonAgent: ChildProcessWithoutNullStreams | null = null;
let currentProjectId: string | null = null;
let serverUrl = 'http://localhost:8000';
let wsUrl = 'ws://localhost:8000/ws/desktop';
let reconnectTimer: NodeJS.Timeout | null = null;
let heartbeatTimer: NodeJS.Timeout | null = null;
let workspaceMap: WorkspaceMap = {};
let currentTaskId: string | null = null;
let currentTaskRunning = false;
let previewWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonAgentRestartCount = 0;
const PYTHON_AGENT_MAX_RESTARTS = 5;
let pythonAgentStopping = false;
let isQuitting = false;
let fullTrustMode = false;

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
    logInfo(`Received protocol URL from second instance: ${url}`);
    if (mainWindow.webContents.isLoading()) {
      mainWindow.webContents.once('did-finish-load', () => {
        mainWindow?.webContents.send('kyrozen:protocol-url', url);
      });
    } else {
      mainWindow.webContents.send('kyrozen:protocol-url', url);
    }
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
let pendingCloudMessages: string[] = [];
let accessToken: string | null = null;
let projectFileWatchers = new Map<string, FSWatcher>();
let pendingFileChanges = new Map<string, NodeJS.Timeout>();
let pythonRuntimePath: string | null = null;
let pythonRuntimeReady = false;

const PROTOCOL_SCHEME = 'kyrozen';
const HEARTBEAT_INTERVAL_MS = 30_000;

const WORKSPACE_CONFIG_PATH = path.join(app.getPath('userData'), 'workspaces.json');
const TOKEN_STORE_PATH = path.join(app.getPath('userData'), 'credentials.json');
const ONBOARDING_CONFIG_PATH = path.join(app.getPath('userData'), 'onboarding.json');

interface OnboardingConfig {
  completed: boolean;
  language: 'zh' | 'en';
  completedAt?: string;
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

async function saveCredentials(
  wsToken: string,
  refreshToken?: string,
  accessToken?: string,
): Promise<void> {
  const payload = JSON.stringify({
    wsToken,
    refreshToken: refreshToken || null,
    accessToken: accessToken || null,
    serverUrl,
  });
  const encrypted = safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(payload) : Buffer.from(payload);
  await fs.mkdir(path.dirname(TOKEN_STORE_PATH), { recursive: true });
  await fs.writeFile(TOKEN_STORE_PATH, encrypted);
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
    const decrypted = safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(raw) : raw.toString();
    const data = JSON.parse(decrypted);
    if (data.wsToken) {
      logInfo('Loaded existing credentials, resuming session');
      return {
        wsToken: data.wsToken,
        refreshToken: data.refreshToken || null,
        accessToken: data.accessToken || null,
        serverUrl: data.serverUrl || 'http://localhost:8000',
      };
    }
  } catch (err: any) {
    logInfo(`No credentials found or failed to load: ${err.message || err}`);
  }
  return null;
}

async function clearCredentials(): Promise<void> {
  try {
    await fs.unlink(TOKEN_STORE_PATH);
  } catch {
    // ignore
  }
}

function showNotification(title: string, body: string) {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show();
  }
}

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
  return pickWorkspaceRoot(projectId);
}

let currentConnectionState: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
let currentConnectionMessage = '未连接';

function updateConnection(state: 'disconnected' | 'connecting' | 'connected' | 'error', message: string) {
  currentConnectionState = state;
  currentConnectionMessage = message;
  logInfo(`Connection state: ${state} - ${message}`);
  mainWindow?.webContents.send('kyrozen:connection-change', state, message);
}

function sendChatMessage(message: { role: string; content: string }) {
  mainWindow?.webContents.send('kyrozen:chat-message', message);
}

function sendExecutionPlan(plan: { task_id: string; steps: string[] }) {
  mainWindow?.webContents.send('kyrozen:execution-plan', plan);
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

app.setAsDefaultProtocolClient(PROTOCOL_SCHEME);

app.whenReady().then(async () => {
  logInfo('App ready, initializing Kyrozen desktop client');
  await loadWorkspaceMap();
  onboardingConfig = await loadOnboardingConfig();
  createWindow();
  createTray();

  const protocolUrl = getProtocolUrl();
  logInfo(`Protocol URL: ${protocolUrl || 'none'}`);
  if (protocolUrl && mainWindow) {
    mainWindow.webContents.once('did-finish-load', () => {
      mainWindow?.webContents.send('kyrozen:protocol-url', protocolUrl);
    });
  } else if (onboardingConfig.completed) {
    // Onboarding already completed: try to resume the previous session from encrypted storage.
    const credentials = await loadCredentials();
    if (credentials) {
      serverUrl = credentials.serverUrl;
      setUpdateApiBaseUrl(serverUrl);
      wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/desktop';
      accessToken = credentials.accessToken;
      connectWebSocket(credentials.wsToken);
      mainWindow?.webContents.once('did-finish-load', () => {
        mainWindow?.webContents.send('kyrozen:session-resumed', credentials.wsToken, credentials.serverUrl);
      });
    }
  } else {
    logInfo('Onboarding not completed; waiting for renderer wizard');
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('open-url', (_event, url) => {
  if (mainWindow?.webContents.isLoading()) {
    mainWindow.webContents.once('did-finish-load', () => {
      mainWindow?.webContents.send('kyrozen:protocol-url', url);
    });
  } else {
    mainWindow?.webContents.send('kyrozen:protocol-url', url);
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
  if (process.platform !== 'darwin') app.quit();
});

async function apiGet(endpoint: string) {
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const response = await fetch(`${serverUrl}${endpoint}`, { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function apiPost(endpoint: string, body: unknown, auth = false) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

/** Download the latest cloud artifacts for a project into <workspace>/.kyrozen/context/. */
async function syncProjectArtifacts(projectId: string): Promise<void> {
  const root = workspaceMap[projectId];
  if (!root || !accessToken) return;

  try {
    const artifacts: Array<{ id: string; type: string; title: string; version: number; updated_at: string }> =
      await apiGet(`/api/projects/${projectId}/artifacts`);
    const contextDir = path.join(root, '.kyrozen', 'context');
    await fs.mkdir(contextDir, { recursive: true });

    const manifest: Array<Record<string, unknown>> = [];
    for (const summary of artifacts) {
      const full: { id: string; type: string; title: string; content: string; version: number; updated_at: string } =
        await apiGet(`/api/projects/${projectId}/artifacts/${summary.id}`);
      const safeTitle = String(full.title || full.type).replace(/[^a-zA-Z0-9\u4e00-\u9fa5._-]/g, '_');
      const fileName = `${safeTitle}.md`;
      const filePath = path.join(contextDir, fileName);
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
    sendChatMessage({
      role: 'system',
      content: `已同步 ${artifacts.length} 个云端 Artifact 到本地 .kyrozen/context`,
    });
  } catch (err: any) {
    sendChatMessage({ role: 'system', content: `Artifact 同步失败: ${err.message || err}` });
  }
}

const KEY_FILE_RE = /(^|\/)(package\.json|readme[^/]*|\.env[^/]*|tsconfig\.json|vite\.config\.[jt]s|tailwind\.config\.[jt]s)$/i;
const SOURCE_FILE_RE = /\.(js|jsx|ts|tsx|py|html|css|vue|svelte)$/i;
const IGNORED_PATH_RE = /[\\/](\.kyrozen|node_modules|\.git|dist|build)[\\/]/;

function shouldUploadFileSummary(relativePath: string): boolean {
  if (IGNORED_PATH_RE.test(relativePath)) return false;
  const lower = relativePath.toLowerCase();
  if (KEY_FILE_RE.test(lower)) return true;
  if (SOURCE_FILE_RE.test(lower)) return true;
  return false;
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
    snippet = content.length > 4000 ? content.slice(0, 4000) + '\n...' : content;
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
    sendChatMessage({ role: 'system', content: `文件摘要同步失败: ${err.message || err}` });
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
      },
    );
    projectFileWatchers.set(projectId, watcher);
  } catch (err: any) {
    sendChatMessage({ role: 'system', content: `无法监听项目文件: ${err.message || err}` });
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
    serverUrl = url.replace(/\/$/, '');
    setUpdateApiBaseUrl(serverUrl);
    wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/desktop';
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
    accessToken = data.access_token || null;
    logInfo(`Signin success, verifying desktop token`);
    await saveCredentials(verify.ws_token, verify.refresh_token, accessToken || undefined);
    connectWebSocket(verify.ws_token);
    logInfo(`Login complete, wsToken acquired`);
    return { success: true, wsToken: verify.ws_token };
  } catch (err: any) {
    logError(`Login failed: ${err.message || err}`);
    return { success: false, error: err.message || '登录失败' };
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
    await saveOnboardingConfig({ completed: true, completedAt: new Date().toISOString() });
    connectWebSocket(data.ws_token);
    return { wsToken: data.ws_token, refreshToken: data.refresh_token };
  } catch (err: any) {
    logError(`Open token verification failed: ${err.message || err}`);
    updateConnection('error', err.message || '令牌验证失败');
    return null;
  }
});

ipcMain.handle('kyrozen:set-current-project', async (_event, projectId: string) => {
  if (currentProjectId && currentProjectId !== projectId) {
    stopWatchingProjectFiles(currentProjectId);
  }
  currentProjectId = projectId;
  const root = await getWorkspaceRoot(projectId);
  if (root) {
    sendChatMessage({ role: 'system', content: `项目工作目录：${root}` });
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

function isPathInside(parent: string, target: string): boolean {
  const relative = path.relative(parent, target);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
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

ipcMain.handle('kyrozen:read-file', async (_event, projectId: string, relativePath: string) => {
  try {
    const root = workspaceMap[projectId];
    if (!root) return { content: '', error: 'No workspace mapped' };
    const target = path.resolve(root, relativePath);
    if (!isPathInside(root, target)) {
      return { content: '', error: 'Path outside workspace' };
    }
    const content = await fs.readFile(target, 'utf-8');
    return { content };
  } catch (err: any) {
    return { content: '', error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:save-file', async (_event, projectId: string, relativePath: string, content: string) => {
  try {
    const root = workspaceMap[projectId];
    if (!root) return { success: false, error: 'No workspace mapped' };
    const target = path.resolve(root, relativePath);
    if (!isPathInside(root, target)) {
      return { success: false, error: 'Path outside workspace' };
    }
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content, 'utf-8');
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
});

ipcMain.handle('kyrozen:get-projects', async () => {
  if (!accessToken) {
    logWarn('get-projects called without access token');
    return [];
  }
  try {
    const list = await apiGet('/api/projects');
    logInfo(`Loaded ${Array.isArray(list) ? list.length : 0} projects from cloud`);
    return list;
  } catch (err: any) {
    logError(`Failed to load projects: ${err.message || err}`);
    sendChatMessage({ role: 'system', content: `获取项目列表失败: ${err.message || err}` });
    return [];
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

ipcMain.handle('kyrozen:get-full-trust', () => {
  return { enabled: fullTrustMode };
});

ipcMain.handle('kyrozen:set-full-trust', (_event, enabled: boolean) => {
  fullTrustMode = Boolean(enabled);
  logWarn(`Full-trust mode ${fullTrustMode ? 'enabled' : 'disabled'} by user`);
  if (fullTrustMode) {
    showNotification(
      '已开启完全信任模式',
      '本次会话内高危工具将自动执行，不再弹出确认对话框。'
    );
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
    const arduino = await ensureArduinoCLI((msg) => sendChatMessage({ role: 'system', content: msg }));
    const pio = await ensurePlatformIO((msg) => sendChatMessage({ role: 'system', content: msg }));
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
    await installCommonCores((msg) => sendChatMessage({ role: 'system', content: msg }));
    return { success: true };
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

ipcMain.handle('kyrozen:get-onboarding-status', async () => {
  onboardingConfig = await loadOnboardingConfig();
  return { ...onboardingConfig };
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

ipcMain.on('kyrozen:request-initial-token', () => {
  const url = getProtocolUrl();
  logInfo(`Renderer requested initial token, protocolUrl=${url || 'none'}`);
  if (url) {
    mainWindow?.webContents.send('kyrozen:protocol-url', url);
  }
  // Send the current connection state in case the renderer missed earlier events
  // (for example, when resuming a saved session before the window finished loading).
  mainWindow?.webContents.send('kyrozen:connection-change', currentConnectionState, currentConnectionMessage);
});

ipcMain.on('kyrozen:send-chat', (_event, message: string) => {
  sendToCloud({
    type: 'task_result',
    task_id: `task_${Date.now()}`,
    status: 'pending',
    result: { message },
  });
});

ipcMain.on('kyrozen:cancel-task', () => {
  if (currentTaskId && currentTaskRunning) {
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'cancel_task',
      params: { task_id: currentTaskId },
    });
  }
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
      updateConnection('connected', '已连接云端');
      pythonAgentRestartCount = 0;
      startHeartbeat();
      flushPendingCloudMessages();
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
      logWarn(`WebSocket closed: code=${code}, reason=${reason.toString() || 'none'}`);
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

function scheduleReconnect(token: string) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket(token);
  }, 5000);
}

/** Route messages from the cloud to the local Python Agent or UI. */
async function handleServerMessage(message: Record<string, unknown>) {
  const type = message.type as string;
  logInfo(`Received server message: ${type}`);

  if (type === 'assign_task') {
    currentTaskId = String(message.task_id);
    currentTaskRunning = true;
    const payload = {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'run_task',
      params: {
        task_id: message.task_id,
        project_id: message.project_id,
        message: message.message,
        mode: message.mode,
        workspace_root: await chooseWorkspaceRoot(String(message.project_id || currentProjectId)),
      },
    };
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
  // main.js is inside dist-electron/main/, which is under desktop/; repo root is one level above desktop.
  return path.resolve(currentDir, '../../../');
}

/** Spawn the local Python Agent process and wire stdio JSON-RPC to the UI/cloud. */
async function startPythonAgent() {
  logInfo('Starting Python Agent');
  stopPythonAgent();

  let pythonPath = process.env.KYROZEN_PYTHON_PATH;
  if (!pythonPath) {
    if (!pythonRuntimeReady) {
      sendChatMessage({ role: 'system', content: '正在准备本地 Python 运行时...' });
      try {
        pythonRuntimePath = await ensurePythonRuntime(getRepoRoot(), (msg) => {
          sendChatMessage({ role: 'system', content: msg });
        });
        pythonRuntimeReady = true;
        if (pythonRuntimePath) {
          sendChatMessage({ role: 'system', content: `使用内置 Python 运行时: ${pythonRuntimePath}` });
        }
      } catch (err: any) {
        sendChatMessage({ role: 'system', content: `内置 Python 运行时准备失败，将尝试系统 python3: ${err.message || err}` });
        pythonRuntimePath = null;
        pythonRuntimeReady = true;
      }
    }
    pythonPath = pythonRuntimePath || 'python3';
  }

  const extraEnv: Record<string, string> = {
    KYROZEN_WS_URL: wsUrl,
    KYROZEN_DESKTOP_MODE: '1',
  };

  if (pythonRuntimePath) {
    setPythonExe(pythonRuntimePath);
    // Resolve hardware toolchain paths before spawning the Agent so that the
    // bundled tools are discoverable by HardwareBridge via environment vars.
    try {
      const arduino = await ensureArduinoCLI((msg) => sendChatMessage({ role: 'system', content: msg }));
      if (arduino.path) {
        extraEnv.KYROZEN_ARDUINO_CLI_PATH = arduino.path;
      }
    } catch (err: any) {
      sendChatMessage({ role: 'system', content: `Arduino CLI 准备失败: ${err.message || err}` });
    }
    try {
      const pio = await ensurePlatformIO((msg) => sendChatMessage({ role: 'system', content: msg }));
      if (pio.path) {
        extraEnv.KYROZEN_PIO_PATH = pio.path;
      }
    } catch (err: any) {
      sendChatMessage({ role: 'system', content: `PlatformIO 准备失败: ${err.message || err}` });
    }
  }

  const agentScript = process.env.KYROZEN_AGENT_SCRIPT || path.join(currentDir, '../../python_agent/main.py');
  logInfo(`Spawning Python Agent: ${pythonPath} ${agentScript}`);

  pythonAgent = spawn(pythonPath, [agentScript], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      ...extraEnv,
    },
  });

  pythonAgent.stdout.on('data', (data: Buffer) => {
    const lines = data.toString().split('\n').filter(Boolean);
    for (const line of lines) {
      handlePythonAgentLine(line);
    }
  });

  pythonAgent.stderr.on('data', (data: Buffer) => {
    sendChatMessage({ role: 'system', content: `Agent: ${data.toString().trim()}` });
  });

  pythonAgent.on('error', (err) => {
    logError(`Python Agent spawn error: ${err.message}`);
    sendChatMessage({ role: 'system', content: `Agent 启动失败: ${err.message}` });
  });

  pythonAgent.on('exit', (code) => {
    logWarn(`Python Agent exited with code ${code ?? 'unknown'}`);
    sendChatMessage({ role: 'system', content: `Python Agent 已退出 (code ${code ?? 'unknown'})` });
    pythonAgent = null;
    if (!pythonAgentStopping && code !== 0) {
      if (pythonAgentRestartCount < PYTHON_AGENT_MAX_RESTARTS) {
        pythonAgentRestartCount += 1;
        const delay = Math.min(5000 * pythonAgentRestartCount, 30000);
        sendChatMessage({ role: 'system', content: `Python Agent 异常退出，${delay / 1000} 秒后尝试重启 (${pythonAgentRestartCount}/${PYTHON_AGENT_MAX_RESTARTS})...` });
        setTimeout(() => {
          if (wsClient?.readyState === WebSocket.OPEN) {
            startPythonAgent();
          }
        }, delay);
      } else {
        sendChatMessage({ role: 'system', content: 'Python Agent 连续异常退出超过最大重试次数，请检查环境后手动重启客户端。' });
        showNotification('Kyrozen', '本地 Agent 无法启动，请检查 Python 环境');
      }
    }
    pythonAgentStopping = false;
  });
}

function stopPythonAgent() {
  if (pythonAgent) {
    pythonAgentStopping = true;
    pythonAgent.kill();
    pythonAgent = null;
  }
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
    if (message.method === 'task_step') {
      const step = message.params.step || {};
      sendToCloud({ type: 'task_step', task_id: message.params.task_id, step });
      sendChatMessage({ role: 'assistant', content: `[${step.status}] ${step.description}` });
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
        sendChatMessage({ role: 'system', content: `已打开预览：${url}` });
      }
    } else if (message.method === 'execution_plan') {
      sendExecutionPlan({
        task_id: String(message.params.task_id || currentTaskId || ''),
        steps: Array.isArray(message.params.steps) ? message.params.steps : [],
      });
    } else if (message.method === 'task_result') {
      currentTaskRunning = false;
      sendToCloud({
        type: 'task_result',
        task_id: message.params.task_id,
        status: message.params.status,
        result: message.params.result,
        steps: message.params.steps,
      });
      const status = message.params.status;
      const answer = message.params.result?.answer || '任务完成';
      sendChatMessage({ role: 'assistant', content: answer });
      if (status === 'failed') {
        showNotification('Kyrozen', '任务执行失败');
      } else if (status === 'cancelled') {
        showNotification('Kyrozen', '任务已取消');
      } else if (status === 'completed') {
        showNotification('Kyrozen', '任务已完成');
      }
    }
  } catch {
    sendChatMessage({ role: 'system', content: line });
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

async function showConfirmationDialog(params: Record<string, unknown>) {
  // When the user has explicitly enabled full-trust mode for this session,
  // skip the dialog and tell the local agent to trust all confirmations.
  if (fullTrustMode) {
    logWarn(`Auto-confirming ${params.tool}.${params.action} because full-trust mode is enabled`);
    sendToPythonAgent({
      jsonrpc: '2.0',
      method: 'confirmation_response',
      params: {
        confirmation_id: params.confirmation_id,
        confirmed: true,
        trust_for_session: true,
        task_id: params.task_id,
      },
    });
    return;
  }

  const result = await dialog.showMessageBox(mainWindow!, {
    type: 'warning',
    buttons: ['确认并信任本次会话', '确认', '取消'],
    defaultId: 2,
    cancelId: 2,
    title: '高危操作确认',
    message: `${params.tool}.${params.action}`,
    detail: `参数：${JSON.stringify(params.parameters, null, 2)}\n原因：${params.reason || '无'}`,
  });
  const confirmed = result.response === 0 || result.response === 1;
  const trustForSession = result.response === 0;
  sendToPythonAgent({
    jsonrpc: '2.0',
    method: 'confirmation_response',
    params: {
      confirmation_id: params.confirmation_id,
      confirmed,
      trust_for_session: trustForSession,
      task_id: params.task_id,
    },
  });
}
