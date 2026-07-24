import { contextBridge, ipcRenderer } from 'electron';

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

contextBridge.exposeInMainWorld('kyrozen', {
  login: (email: string, password: string, serverUrl: string) =>
    ipcRenderer.invoke('kyrozen:login', email, password, serverUrl),

  verifyOpenToken: (token: string) => ipcRenderer.invoke('kyrozen:verify-open-token', token),

  setCurrentProject: (projectId: string) => ipcRenderer.invoke('kyrozen:set-current-project', projectId),
  pickWorkspace: (projectId: string) => ipcRenderer.invoke('kyrozen:pick-workspace', projectId),
  getWorkspaceRoot: (projectId: string) => ipcRenderer.invoke('kyrozen:get-workspace-root', projectId),

  requestInitialToken: () => ipcRenderer.send('kyrozen:request-initial-token'),

  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) =>
    ipcRenderer.on('kyrozen:connection-change', (_event, state, message) => callback(state, message)),

  onProtocolUrl: (callback: (url: string) => void) =>
    ipcRenderer.on('kyrozen:protocol-url', (_event, url) => callback(url)),

  sendChat: (message: string) => ipcRenderer.send('kyrozen:send-chat', message),

  onChatMessage: (callback: (message: { role: string; content: string }) => void) =>
    ipcRenderer.on('kyrozen:chat-message', (_event, message) => callback(message)),
});
