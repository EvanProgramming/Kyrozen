import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import path from 'path';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import WebSocket from 'ws';

const isDev = process.env.NODE_ENV === 'development';
let mainWindow: BrowserWindow | null = null;
let wsClient: WebSocket | null = null;
let pythonAgent: ChildProcessWithoutNullStreams | null = null;
let currentProjectId: string | null = null;
let serverUrl = 'http://localhost:8000';
let wsUrl = 'ws://localhost:8000/ws/desktop';
let reconnectTimer: NodeJS.Timeout | null = null;

const PROTOCOL_SCHEME = 'kyrozen';

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
}

function getProtocolUrl() {
  const args = process.argv.slice(1);
  return args.find((arg) => arg.startsWith(`${PROTOCOL_SCHEME}://`)) || null;
}

app.setAsDefaultProtocolClient(PROTOCOL_SCHEME);

app.whenReady().then(() => {
  createWindow();

  const protocolUrl = getProtocolUrl();
  if (protocolUrl && mainWindow) {
    mainWindow.webContents.once('did-finish-load', () => {
      mainWindow?.webContents.send('kyrozen:protocol-url', protocolUrl);
    });
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
    connectWebSocket(data.ws_token);
    return { wsToken: data.ws_token, refreshToken: data.refresh_token };
  } catch (err: any) {
    updateConnection('error', err.message || '令牌验证失败');
    return null;
  }
});

ipcMain.on('kyrozen:set-current-project', (_event, projectId: string) => {
  currentProjectId = projectId;
  wsClient?.send(JSON.stringify({ type: 'heartbeat', active_project_id: projectId }));
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
  if (wsClient) {
    wsClient.removeAllListeners();
    wsClient.close();
    wsClient = null;
  }
}

function scheduleReconnect(token: string) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket(token);
  }, 5000);
}

async function handleServerMessage(message: Record<string, unknown>) {
  const type = message.type as string;

  if (type === 'assign_task') {
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
  if (!projectId) return path.join(require('os').homedir(), 'KyrozenProjects');
  const root = path.join(require('os').homedir(), 'KyrozenProjects', projectId);
  await require('fs/promises').mkdir(root, { recursive: true });
  return root;
}

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
  });
}

function stopPythonAgent() {
  if (pythonAgent) {
    pythonAgent.kill();
    pythonAgent = null;
  }
}

function sendToPythonAgent(payload: unknown) {
  if (!pythonAgent) return;
  pythonAgent.stdin.write(JSON.stringify(payload) + '\n');
}

function handlePythonAgentLine(line: string) {
  try {
    const message = JSON.parse(line);
    if (message.method === 'task_step') {
      const step = message.params.step || {};
      wsClient?.send(JSON.stringify({ type: 'task_step', task_id: message.params.task_id, step }));
      sendChatMessage({ role: 'assistant', content: `[${step.status}] ${step.description}` });
    } else if (message.method === 'request_confirmation') {
      showConfirmationDialog(message.params);
    } else if (message.method === 'model_request') {
      wsClient?.send(JSON.stringify(message.params));
    } else if (message.method === 'task_result') {
      wsClient?.send(
        JSON.stringify({
          type: 'task_result',
          task_id: message.params.task_id,
          status: message.params.status,
          result: message.params.result,
          steps: message.params.steps,
        })
      );
      sendChatMessage({ role: 'assistant', content: message.params.result?.answer || '任务完成' });
    }
  } catch {
    sendChatMessage({ role: 'system', content: line });
  }
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
    id: params.confirmation_id || Date.now(),
    result: { confirmed },
  });
}
