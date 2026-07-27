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
  getServerUrl: () => ipcRenderer.invoke('kyrozen:get-server-url'),
  setServerUrl: (url: string) => ipcRenderer.invoke('kyrozen:set-server-url', url),
  getFullTrust: () => ipcRenderer.invoke('kyrozen:get-full-trust'),
  setFullTrust: (enabled: boolean) => ipcRenderer.invoke('kyrozen:set-full-trust', enabled),

  listFiles: (projectId: string) => ipcRenderer.invoke('kyrozen:list-files', projectId),
  readFile: (projectId: string, relativePath: string) => ipcRenderer.invoke('kyrozen:read-file', projectId, relativePath),
  searchAcrossProjects: (query: string, options?: { maxResults?: number; includeContent?: boolean }) =>
    ipcRenderer.invoke('kyrozen:search-across-projects', query, options),
  saveFile: (projectId: string, relativePath: string, content: string) =>
    ipcRenderer.invoke('kyrozen:save-file', projectId, relativePath, content),

  requestInitialToken: () => ipcRenderer.send('kyrozen:request-initial-token'),

  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) => {
    const handler = (_event: unknown, state: ConnectionState, message: string) => callback(state, message);
    ipcRenderer.on('kyrozen:connection-change', handler);
    return () => ipcRenderer.removeListener('kyrozen:connection-change', handler);
  },

  onProtocolUrl: (callback: (url: string) => void) => {
    const handler = (_event: unknown, url: string) => callback(url);
    ipcRenderer.on('kyrozen:protocol-url', handler);
    return () => ipcRenderer.removeListener('kyrozen:protocol-url', handler);
  },

  onSessionResumed: (callback: (token: string, serverUrl: string) => void) => {
    const handler = (_event: unknown, token: string, serverUrl: string) => callback(token, serverUrl);
    ipcRenderer.on('kyrozen:session-resumed', handler);
    return () => ipcRenderer.removeListener('kyrozen:session-resumed', handler);
  },

  onSessionEnded: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on('kyrozen:session-ended', handler);
    return () => ipcRenderer.removeListener('kyrozen:session-ended', handler);
  },

  onOpenSettings: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on('kyrozen:open-settings', handler);
    return () => ipcRenderer.removeListener('kyrozen:open-settings', handler);
  },

  sendChat: (message: string) => ipcRenderer.send('kyrozen:send-chat', message),
  cancelTask: () => ipcRenderer.send('kyrozen:cancel-task'),
  startPairing: (serverUrl: string) => ipcRenderer.invoke('kyrozen:start-pairing', serverUrl),
  pollPairing: (serverUrl: string, code: string) => ipcRenderer.invoke('kyrozen:poll-pairing', serverUrl, code),

  onChatMessage: (callback: (message: { role: string; content: string; raw?: string }) => void) => {
    const handler = (_event: unknown, message: { role: string; content: string; raw?: string }) => callback(message);
    ipcRenderer.on('kyrozen:chat-message', handler);
    return () => ipcRenderer.removeListener('kyrozen:chat-message', handler);
  },

  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) => {
    const handler = (_event: unknown, plan: { task_id: string; steps: string[] }) => callback(plan);
    ipcRenderer.on('kyrozen:execution-plan', handler);
    return () => ipcRenderer.removeListener('kyrozen:execution-plan', handler);
  },

  openPreview: (url: string, mode: 'embedded' | 'window' | 'external') =>
    ipcRenderer.invoke('kyrozen:open-preview', url, mode),

  onOpenPreviewUrl: (callback: (url: string) => void) => {
    const handler = (_event: unknown, url: string) => callback(url);
    ipcRenderer.on('kyrozen:open-preview-url', handler);
    return () => ipcRenderer.removeListener('kyrozen:open-preview-url', handler);
  },

  checkForUpdates: () => ipcRenderer.invoke('kyrozen:check-for-updates'),

  onUpdateStatus: (callback: (status: { status: string; message: string }) => void) => {
    const handler = (_event: unknown, status: { status: string; message: string }) => callback(status);
    ipcRenderer.on('kyrozen:update-status', handler);
    return () => ipcRenderer.removeListener('kyrozen:update-status', handler);
  },

  onGitHubStatus: (callback: (status: { connected: boolean; scope?: string }) => void) => {
    const handler = (_event: unknown, status: { connected: boolean; scope?: string }) => callback(status);
    ipcRenderer.on('kyrozen:github-status', handler);
    return () => ipcRenderer.removeListener('kyrozen:github-status', handler);
  },

  onFullTrustChange: (callback: (status: { enabled: boolean }) => void) => {
    const handler = (_event: unknown, status: { enabled: boolean }) => callback(status);
    ipcRenderer.on('kyrozen:full-trust-change', handler);
    return () => ipcRenderer.removeListener('kyrozen:full-trust-change', handler);
  },

  ensureHardwareToolchain: () => ipcRenderer.invoke('kyrozen:ensure-hardware-toolchain'),
  installCommonCores: () => ipcRenderer.invoke('kyrozen:install-common-cores'),
  checkHardwareUpdates: () => ipcRenderer.invoke('kyrozen:check-hardware-updates'),
  getHardwareToolStatus: () => ipcRenderer.invoke('kyrozen:get-hardware-tool-status'),
  connectGitHub: () => ipcRenderer.invoke('kyrozen:connect-github'),
  startGithubLogin: () => ipcRenderer.invoke('kyrozen:start-github-login'),
  getGitHubStatus: () => ipcRenderer.invoke('kyrozen:get-github-status'),
  createGitHubRepo: (name: string, description?: string, isPrivate?: boolean) =>
    ipcRenderer.invoke('kyrozen:create-github-repo', name, description, isPrivate),
  initGitRepo: (remoteUrl?: string) => ipcRenderer.invoke('kyrozen:init-git-repo', remoteUrl),
  getGitStatus: () => ipcRenderer.invoke('kyrozen:get-git-status'),
  commitAndPush: (message: string) => ipcRenderer.invoke('kyrozen:commit-and-push', message),
  setAutoCommit: (enabled: boolean) => ipcRenderer.invoke('kyrozen:set-auto-commit', enabled),
  getAutoCommit: () => ipcRenderer.invoke('kyrozen:get-auto-commit'),

  getOnboardingStatus: () => ipcRenderer.invoke('kyrozen:get-onboarding-status'),
  getOnboardingLanguage: () => ipcRenderer.invoke('kyrozen:get-onboarding-language'),
  saveOnboardingLanguage: (language: 'zh' | 'en') => ipcRenderer.invoke('kyrozen:save-onboarding-language', language),
  completeOnboarding: (language?: 'zh' | 'en') => ipcRenderer.invoke('kyrozen:complete-onboarding', language),

  logout: () => ipcRenderer.invoke('kyrozen:logout'),
  checkPythonRuntime: () => ipcRenderer.invoke('kyrozen:check-python-runtime'),
  ensurePythonRuntime: () => ipcRenderer.invoke('kyrozen:ensure-python-runtime'),
  ensureProjectVenv: () => ipcRenderer.invoke('kyrozen:ensure-project-venv'),
  installProjectDeps: (packages?: string[]) => ipcRenderer.invoke('kyrozen:install-project-deps', packages),
  getProjectVenv: () => ipcRenderer.invoke('kyrozen:get-project-venv'),
  pickOnboardingWorkspace: () => ipcRenderer.invoke('kyrozen:pick-onboarding-workspace'),
  importLocalProject: () => ipcRenderer.invoke('kyrozen:import-local-project'),

  onOnboardingProgress: (callback: (progress: { step: string; message: string }) => void) => {
    const handler = (_event: unknown, progress: { step: string; message: string }) => callback(progress);
    ipcRenderer.on('kyrozen:onboarding-progress', handler);
    return () => ipcRenderer.removeListener('kyrozen:onboarding-progress', handler);
  },
});
