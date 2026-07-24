import { app, BrowserWindow, dialog, ipcMain, Menu, Notification, safeStorage, shell, Tray } from 'electron';
import path from 'path';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs/promises';
import WebSocket from 'ws';

interface WorkspaceMap {
  [projectId: string]: string;
}

const isDev = process.env.NODE_ENV === 'development';
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

const PROTOCOL_SCHEME = 'kyrozen';
const HEARTBEAT_INTERVAL_MS = 30_000;

const WORKSPACE_CONFIG_PATH = path.join(app.getPath('userData'), 'workspaces.json');
const TOKEN_STORE_PATH = path.join(app.getPath('userData'), 'credentials.json');

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

async function saveCredentials(wsToken: string, refreshToken?: string): Promise<void> {
  const payload = JSON.stringify({ wsToken, refreshToken: refreshToken || null, serverUrl });
  const encrypted = safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(payload) : Buffer.from(payload);
  await fs.mkdir(path.dirname(TOKEN_STORE_PATH), { recursive: true });
  await fs.writeFile(TOKEN_STORE_PATH, encrypted);
}

async function loadCredentials(): Promise<{ wsToken: string; refreshToken: string | null; serverUrl: string } | null> {
  try {
    const raw = await fs.readFile(TOKEN_STORE_PATH);
    const decrypted = safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(raw) : raw.toString();
    const data = JSON.parse(decrypted);
    if (data.wsToken) {
      return { wsToken: data.wsToken, refreshToken: data.refreshToken || null, serverUrl: data.serverUrl || 'http://localhost:8000' };
    }
  } catch {
    // ignore missing or corrupt credential store
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

function updateConnection(state: 'disconnected' | 'connecting' | 'connected' | 'error', message: string) {
  mainWindow?.webContents.send('kyrozen:connection-change', state, message);
}

function sendChatMessage(message: { role: string; content: string }) {
  mainWindow?.webContents.send('kyrozen:chat-message', message);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.on('close', (event) => {
    if (process.platform === 'darwin') return;
    event.preventDefault();
    mainWindow?.hide();
  });
}

function createTray() {
  const { nativeImage } = require('electron');
  const iconPath = path.join(__dirname, '../../public/tray-icon.png');
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
    { type: 'separator' },
    {
      label: '退出并清除登录状态',
      click: async () => {
        await clearCredentials();
        disconnectWebSocket();
        stopPythonAgent();
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
  await loadWorkspaceMap();
  createWindow();
  createTray();

  const protocolUrl = getProtocolUrl();
  if (protocolUrl && mainWindow) {
    mainWindow.webContents.once('did-finish-load', () => {
      mainWindow?.webContents.send('kyrozen:protocol-url', protocolUrl);
    });
  } else {
    // No protocol URL: try to resume the previous session from encrypted storage.
    const credentials = await loadCredentials();
    if (credentials) {
      serverUrl = credentials.serverUrl;
      wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/desktop';
      connectWebSocket(credentials.wsToken);
    }
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

app.on('window-all-closed', () => {
  disconnectWebSocket();
  stopPythonAgent();
  if (process.platform !== 'darwin') app.quit();
});

async function apiPost(endpoint: string, body: unknown) {
  const response = await fetch(`${serverUrl}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

ipcMain.handle('kyrozen:login', async (_event, email: string, password: string, url: string) => {
  try {
    serverUrl = url.replace(/\/$/, '');
    wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/desktop';
    const data = await apiPost('/api/auth/signin', { email, password });
    if (!data.access_token) {
      return { success: false, error: '登录失败：未返回 access_token' };
    }

    const verify = await apiPost('/api/desktop/verify-token', {
      access_token: data.access_token,
      device_name: require('os').hostname(),
      client_version: app.getVersion(),
      platform: process.platform,
    });
    await saveCredentials(verify.ws_token, verify.refresh_token);
    connectWebSocket(verify.ws_token);
    return { success: true, wsToken: verify.ws_token };
  } catch (err: any) {
    return { success: false, error: err.message || '登录失败' };
  }
});

ipcMain.handle('kyrozen:verify-open-token', async (_event, token: string) => {
  try {
    const data = await apiPost('/api/desktop/verify-token', {
      token,
      device_name: require('os').hostname(),
      client_version: app.getVersion(),
      platform: process.platform,
    });
    await saveCredentials(data.ws_token, data.refresh_token);
    connectWebSocket(data.ws_token);
    return { wsToken: data.ws_token, refreshToken: data.refresh_token };
  } catch (err: any) {
    updateConnection('error', err.message || '令牌验证失败');
    return null;
  }
});

ipcMain.handle('kyrozen:set-current-project', async (_event, projectId: string) => {
  currentProjectId = projectId;
  const root = await getWorkspaceRoot(projectId);
  if (root) {
    sendChatMessage({ role: 'system', content: `项目工作目录：${root}` });
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

ipcMain.on('kyrozen:request-initial-token', () => {
  const url = getProtocolUrl();
  if (url) {
    mainWindow?.webContents.send('kyrozen:protocol-url', url);
  }
});

ipcMain.on('kyrozen:send-chat', (_event, message: string) => {
  wsClient?.send(
    JSON.stringify({
      type: 'task_result',
      task_id: `task_${Date.now()}`,
      status: 'pending',
      result: { message },
    })
  );
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

  try {
    wsClient = new WebSocket(wsUrl);

    wsClient.on('open', () => {
      wsClient?.send(
        JSON.stringify({
          type: 'auth',
          token,
          device_name: require('os').hostname(),
          client_version: app.getVersion(),
          platform: process.platform,
          current_project_id: currentProjectId,
        })
      );
      updateConnection('connected', '已连接云端');
      pythonAgentRestartCount = 0;
      startHeartbeat();
      startPythonAgent();
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
      updateConnection('error', `WebSocket 错误: ${err.message}`);
    });

    wsClient.on('close', () => {
      updateConnection('disconnected', '连接已断开，5 秒后重连');
      scheduleReconnect(token);
    });
  } catch (err: any) {
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

/** Spawn the local Python Agent process and wire stdio JSON-RPC to the UI/cloud. */
function startPythonAgent() {
  stopPythonAgent();
  const pythonPath = process.env.KYROZEN_PYTHON_PATH || 'python3';
  const agentScript = process.env.KYROZEN_AGENT_SCRIPT || path.join(__dirname, '../../python_agent/main.py');

  pythonAgent = spawn(pythonPath, [agentScript], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      KYROZEN_WS_URL: wsUrl,
      KYROZEN_DESKTOP_MODE: '1',
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

  pythonAgent.on('exit', (code) => {
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

/** Parse one JSON-RPC line from the Python Agent and dispatch it. */
function handlePythonAgentLine(line: string) {
  try {
    const message = JSON.parse(line);
    if (message.method === 'task_step') {
      const step = message.params.step || {};
      wsClient?.send(JSON.stringify({ type: 'task_step', task_id: message.params.task_id, step }));
      sendChatMessage({ role: 'assistant', content: `[${step.status}] ${step.description}` });
    } else if (message.method === 'request_confirmation') {
      showConfirmationDialog(message.params);
      showNotification('Kyrozen', `请求确认：${message.params.tool}.${message.params.action}`);
    } else if (message.method === 'model_request') {
      wsClient?.send(JSON.stringify(message.params));
    } else if (message.method === 'open_preview') {
      const url = String(message.params.url || '');
      if (url) {
        openPreviewWindow(url);
        sendChatMessage({ role: 'system', content: `已打开预览：${url}` });
      }
    } else if (message.method === 'task_result') {
      currentTaskRunning = false;
      wsClient?.send(
        JSON.stringify({
          type: 'task_result',
          task_id: message.params.task_id,
          status: message.params.status,
          result: message.params.result,
          steps: message.params.steps,
        })
      );
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

async function showConfirmationDialog(params: Record<string, unknown>) {
  const result = await dialog.showMessageBox(mainWindow!, {
    type: 'warning',
    buttons: ['确认', '取消'],
    defaultId: 1,
    cancelId: 1,
    title: '高危操作确认',
    message: `${params.tool}.${params.action}`,
    detail: `参数：${JSON.stringify(params.parameters, null, 2)}\n原因：${params.reason || '无'}`,
  });
  const confirmed = result.response === 0;
  sendToPythonAgent({
    jsonrpc: '2.0',
    method: 'confirmation_response',
    params: {
      confirmation_id: params.confirmation_id,
      confirmed,
      task_id: params.task_id,
    },
  });
}
