import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload script for the Kyrozen desktop client.
 *
 * It exposes a minimal, typed API on `window.kyrozen` so the renderer process
 * can communicate with the Electron main process without direct Node.js access.
 */

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

contextBridge.exposeInMainWorld('kyrozen', {
  login: (email: string, password: string, serverUrl: string) =>
    ipcRenderer.invoke('kyrozen:login', email, password, serverUrl),

  verifyOpenToken: (token: string) => ipcRenderer.invoke('kyrozen:verify-open-token', token),

  setCurrentProject: (projectId: string) => ipcRenderer.invoke('kyrozen:set-current-project', projectId),
  pickWorkspace: (projectId: string) => ipcRenderer.invoke('kyrozen:pick-workspace', projectId),
  getWorkspaceRoot: (projectId: string) => ipcRenderer.invoke('kyrozen:get-workspace-root', projectId),
  getProjects: () => ipcRenderer.invoke('kyrozen:get-projects'),

  getQuota: () => ipcRenderer.invoke('kyrozen:get-quota'),
  getFullTrust: () => ipcRenderer.invoke('kyrozen:get-full-trust'),
  setFullTrust: (enabled: boolean) => ipcRenderer.invoke('kyrozen:set-full-trust', enabled),

  listFiles: (projectId: string) => ipcRenderer.invoke('kyrozen:list-files', projectId),
  readFile: (projectId: string, relativePath: string) => ipcRenderer.invoke('kyrozen:read-file', projectId, relativePath),
  saveFile: (projectId: string, relativePath: string, content: string) =>
    ipcRenderer.invoke('kyrozen:save-file', projectId, relativePath, content),

  requestInitialToken: () => ipcRenderer.send('kyrozen:request-initial-token'),

  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) =>
    ipcRenderer.on('kyrozen:connection-change', (_event, state, message) => callback(state, message)),

  onProtocolUrl: (callback: (url: string) => void) =>
    ipcRenderer.on('kyrozen:protocol-url', (_event, url) => callback(url)),

  onSessionResumed: (callback: (token: string, serverUrl: string) => void) =>
    ipcRenderer.on('kyrozen:session-resumed', (_event, token, serverUrl) => callback(token, serverUrl)),

  sendChat: (message: string) => ipcRenderer.send('kyrozen:send-chat', message),
  cancelTask: () => ipcRenderer.send('kyrozen:cancel-task'),

  onChatMessage: (callback: (message: { role: string; content: string }) => void) =>
    ipcRenderer.on('kyrozen:chat-message', (_event, message) => callback(message)),

  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) =>
    ipcRenderer.on('kyrozen:execution-plan', (_event, plan) => callback(plan)),

  openPreview: (url: string, mode: 'embedded' | 'window' | 'external') =>
    ipcRenderer.invoke('kyrozen:open-preview', url, mode),

  onOpenPreviewUrl: (callback: (url: string) => void) =>
    ipcRenderer.on('kyrozen:open-preview-url', (_event, url) => callback(url)),

  checkForUpdates: () => ipcRenderer.invoke('kyrozen:check-for-updates'),

  onUpdateStatus: (callback: (status: { status: string; message: string }) => void) =>
    ipcRenderer.on('kyrozen:update-status', (_event, status) => callback(status)),

  ensureHardwareToolchain: () => ipcRenderer.invoke('kyrozen:ensure-hardware-toolchain'),
  installCommonCores: () => ipcRenderer.invoke('kyrozen:install-common-cores'),
  connectGitHub: () => ipcRenderer.invoke('kyrozen:connect-github'),
});
