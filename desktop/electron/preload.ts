import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload script for the Kyrozen desktop client.
 *
 * It exposes a minimal, typed API on `window.kyrozen` so the renderer process
 * can communicate with the Electron main process without direct Node.js access.
 */

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

type SoftwareFeatureResult = Record<string, unknown>;

type PlanStepStatus = 'pending' | 'in_progress' | 'completed' | 'failed';
type PlanStep = { id: string; title: string; detail?: string; status: PlanStepStatus };
type PlanPayload = { stage?: string; title?: string; goal?: string; task_id?: string; steps?: PlanStep[] };

contextBridge.exposeInMainWorld('kyrozen', {
  login: (email: string, password: string, serverUrl: string) =>
    ipcRenderer.invoke('kyrozen:login', email, password, serverUrl),

  verifyOpenToken: (token: string) => ipcRenderer.invoke('kyrozen:verify-open-token', token),
  loadChatMessages: (projectId: string) => ipcRenderer.invoke('kyrozen:load-chat-messages', projectId),

  setCurrentProject: (projectId: string) => ipcRenderer.invoke('kyrozen:set-current-project', projectId),
  pickWorkspace: (projectId: string) => ipcRenderer.invoke('kyrozen:pick-workspace', projectId),
  getWorkspaceRoot: (projectId: string) => ipcRenderer.invoke('kyrozen:get-workspace-root', projectId),
  getProjects: () => ipcRenderer.invoke('kyrozen:get-projects'),
  createProject: (name: string, description?: string, goal?: string) =>
    ipcRenderer.invoke('kyrozen:create-project', name, description, goal),
  renameProject: (projectId: string, name: string) =>
    ipcRenderer.invoke('kyrozen:rename-project', projectId, name),
  openProjectInFinder: (projectId: string) =>
    ipcRenderer.invoke('kyrozen:open-project-in-finder', projectId),
  deleteProject: (projectId: string) =>
    ipcRenderer.invoke('kyrozen:delete-project', projectId),
  getProjectState: (projectId: string) => ipcRenderer.invoke('kyrozen:get-project-state', projectId),
  getProjectWorkspace: (projectId: string) => ipcRenderer.invoke('kyrozen:get-project-workspace', projectId),
  createArtifact: (projectId: string, type: string, title: string, content: string, changeReason?: string) =>
    ipcRenderer.invoke('kyrozen:create-artifact', projectId, type, title, content, changeReason || ''),
  createEvidence: (projectId: string, evidence: Record<string, unknown>) =>
    ipcRenderer.invoke('kyrozen:create-evidence', projectId, evidence),
  runResearch: (projectId: string, query: string, limit = 5) =>
    ipcRenderer.invoke('kyrozen:run-research', projectId, query, limit),
  evidenceImpact: (projectId: string, artifactId: string) =>
    ipcRenderer.invoke('kyrozen:evidence-impact', projectId, artifactId),
  deleteEvidence: (projectId: string, artifactId: string, expectedVersion?: number) =>
    ipcRenderer.invoke('kyrozen:delete-evidence', projectId, artifactId, expectedVersion),
  editEvidence: (projectId: string, artifactId: string, evidence: Record<string, unknown>, expectedVersion?: number) =>
    ipcRenderer.invoke('kyrozen:edit-evidence', projectId, artifactId, evidence, expectedVersion),
  updateEvidence: (projectId: string, artifactId: string, status: 'active' | 'invalid' | 'deleted', expectedVersion?: number) =>
    ipcRenderer.invoke('kyrozen:update-evidence', projectId, artifactId, status, expectedVersion),
  mergeEvidence: (projectId: string, artifactId: string, targetEvidenceId: string, expectedSourceVersion?: number, expectedTargetVersion?: number) =>
    ipcRenderer.invoke('kyrozen:merge-evidence', projectId, artifactId, targetEvidenceId, expectedSourceVersion, expectedTargetVersion),
  getSolutions: (projectId: string) => ipcRenderer.invoke('kyrozen:get-solutions', projectId),
  saveSolution: (projectId: string, comparison: Record<string, unknown>, action: string, affectedTasks: string[] = []) =>
    ipcRenderer.invoke('kyrozen:save-solution', projectId, comparison, action, affectedTasks),
  confirmProtocol: (projectId: string, protocol: Record<string, unknown>, confirmed = true, affectedFiles: string[] = [], affectedTasks: string[] = []) =>
    ipcRenderer.invoke('kyrozen:confirm-protocol', projectId, protocol, confirmed, affectedFiles, affectedTasks),
  confirmWorkflow: (projectId: string, projectType: 'software' | 'embedded' | 'hybrid') =>
    ipcRenderer.invoke('kyrozen:confirm-workflow', projectId, projectType),
  advanceHybridTrack: (projectId: string, track: string, expectedVersion?: number) =>
    ipcRenderer.invoke('kyrozen:advance-hybrid-track', projectId, track, expectedVersion),
  runLocalHardware: (projectId: string, workspaceRoot: string, action: string, options?: { board?: string; port?: string; baud?: number; transport?: string; message?: Record<string, unknown> }) =>
    ipcRenderer.invoke('kyrozen:run-local-hardware', projectId, workspaceRoot, action, options || {}),
  runProtocolScenarios: (projectId: string) => ipcRenderer.invoke('kyrozen:run-protocol-scenarios', projectId),
  createDecision: (projectId: string, decision: string, reason: string) =>
    ipcRenderer.invoke('kyrozen:create-decision', projectId, decision, reason),
  createFeedback: (projectId: string, description: string, type: string, priority: string, validation?: Record<string, unknown>) =>
    ipcRenderer.invoke('kyrozen:create-feedback', projectId, description, type, priority, validation || {}),
  updateSuggestionStatus: (projectId: string, suggestionId: string, status: string) =>
    ipcRenderer.invoke('kyrozen:update-suggestion-status', projectId, suggestionId, status),
  deleteLearningItem: (projectId: string, kind: string, itemId: string) =>
    ipcRenderer.invoke('kyrozen:delete-learning-item', projectId, kind, itemId),
  exportProject: (projectId: string) => ipcRenderer.invoke('kyrozen:export-project', projectId),

  getQuota: () => ipcRenderer.invoke('kyrozen:get-quota'),
  startAfdianConnect: () => ipcRenderer.invoke('kyrozen:start-afdian-connect'),
  startAfdianCheckout: (plan: 'lite' | 'pro' | 'ultimate') => ipcRenderer.invoke('kyrozen:start-afdian-checkout', plan),
  getAfdianPaymentStatus: (checkoutId: string) => ipcRenderer.invoke('kyrozen:get-afdian-payment-status', checkoutId),
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
  getInitialSession: () => ipcRenderer.invoke('kyrozen:get-initial-session'),
  getUserProfile: () => ipcRenderer.invoke('kyrozen:get-user-profile'),

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

  onLoginFailed: (callback: (message: string) => void) => {
    const handler = (_event: unknown, message: string) => callback(message);
    ipcRenderer.on('kyrozen:login-failed', handler);
    return () => ipcRenderer.removeListener('kyrozen:login-failed', handler);
  },

  onSessionEnded: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on('kyrozen:session-ended', handler);
    return () => ipcRenderer.removeListener('kyrozen:session-ended', handler);
  },

  onSessionExpired: (callback: (message: string) => void) => {
    const handler = (_event: unknown, message: string) => callback(message);
    ipcRenderer.on('kyrozen:session-expired', handler);
    return () => ipcRenderer.removeListener('kyrozen:session-expired', handler);
  },

  onOpenSettings: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on('kyrozen:open-settings', handler);
    return () => ipcRenderer.removeListener('kyrozen:open-settings', handler);
  },

  sendChat: (message: string, mode?: string) => ipcRenderer.invoke('kyrozen:send-chat', message, mode),
  cancelTask: () => ipcRenderer.send('kyrozen:cancel-task'),
  startPairing: (serverUrl: string) => ipcRenderer.invoke('kyrozen:start-pairing', serverUrl),
  pollPairing: (serverUrl: string, code: string) => ipcRenderer.invoke('kyrozen:poll-pairing', serverUrl, code),

  onChatMessage: (callback: (message: { role: string; content: string; raw?: string; error?: string; operations?: unknown[] }) => void) => {
    const handler = (_event: unknown, message: { role: string; content: string; raw?: string; error?: string; operations?: unknown[] }) => callback(message);
    ipcRenderer.on('kyrozen:chat-message', handler);
    return () => ipcRenderer.removeListener('kyrozen:chat-message', handler);
  },

  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) => {
    const handler = (_event: unknown, plan: { task_id: string; steps: string[] }) => callback(plan);
    ipcRenderer.on('kyrozen:execution-plan', handler);
    return () => ipcRenderer.removeListener('kyrozen:execution-plan', handler);
  },

  onPlanUpdated: (callback: (payload: { task_id: string; plan: PlanPayload; source: string }) => void) => {
    const handler = (_event: unknown, payload: { task_id: string; plan: PlanPayload; source: string }) =>
      callback(payload);
    ipcRenderer.on('kyrozen:plan-updated', handler);
    return () => ipcRenderer.removeListener('kyrozen:plan-updated', handler);
  },

  readWorkspacePlan: (workspaceRoot: string) =>
    ipcRenderer.invoke('kyrozen:read-workspace-plan', workspaceRoot),

  onTaskActivity: (callback: (activity: { task_id: string; description: string; status: string }) => void) => {
    const handler = (_event: unknown, activity: { task_id: string; description: string; status: string }) => callback(activity);
    ipcRenderer.on('kyrozen:task-activity', handler);
    return () => ipcRenderer.removeListener('kyrozen:task-activity', handler);
  },

  onAgentRouted: (callback: (decision: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, decision: Record<string, unknown>) => callback(decision);
    ipcRenderer.on('kyrozen:agent-routed', handler);
    return () => ipcRenderer.removeListener('kyrozen:agent-routed', handler);
  },

  onAgentDegraded: (callback: (info: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, info: Record<string, unknown>) => callback(info);
    ipcRenderer.on('kyrozen:agent-degraded', handler);
    return () => ipcRenderer.removeListener('kyrozen:agent-degraded', handler);
  },

  // P0-03/04/06: surface whether the bundled Python Agent is alive so the UI
  // can stop infinite loading and show a degraded/offline notice.
  onAgentReady: (callback: (info: { status: string; version?: string; mode?: string; code?: number | null; reason?: string; retrying?: boolean }) => void) => {
    const handler = (_event: unknown, info: { status: string; version?: string; mode?: string; code?: number | null; reason?: string; retrying?: boolean }) => callback(info);
    ipcRenderer.on('kyzon:agent-ready', handler);
    return () => ipcRenderer.removeListener('kyzon:agent-ready', handler);
  },

  onStageUpdated: (callback: (status: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, status: Record<string, unknown>) => callback(status);
    ipcRenderer.on('kyrozen:stage-updated', handler);
    return () => ipcRenderer.removeListener('kyrozen:stage-updated', handler);
  },

  // 3.4 status bar: user-facing agent states (Reading/Editing/Running/...).
  onStatusUpdated: (callback: (status: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, status: Record<string, unknown>) => callback(status);
    ipcRenderer.on('kyzen:status-updated', handler);
    return () => ipcRenderer.removeListener('kyzen:status-updated', handler);
  },

  // 3.4 attachments / operation log / confirmation results.
  onInteraction: (callback: (payload: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, payload: Record<string, unknown>) => callback(payload);
    ipcRenderer.on('kyzen:interaction', handler);
    return () => ipcRenderer.removeListener('kyzen:interaction', handler);
  },
  sendInteraction: (params: Record<string, unknown>) =>
    ipcRenderer.send('kyzen:interaction', params),

  // 3.3 real software generation / run / repair panel.
  onSoftwareFeature: (callback: (result: SoftwareFeatureResult) => void) => {
    const handler = (_event: unknown, result: SoftwareFeatureResult) => callback(result);
    ipcRenderer.on('kyzen:software-feature', handler);
    return () => ipcRenderer.removeListener('kyzen:software-feature', handler);
  },
  sendSoftwareFeature: (params: Record<string, unknown>) =>
    ipcRenderer.send('kyzen:software-feature', params),

  sendStageAction: (action: 'refresh' | 'advance_normal' | 'return', stage: string) =>
    ipcRenderer.invoke('kyrozen:stage-action', action, stage),

  onConfirmationRequest: (callback: (request: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, request: Record<string, unknown>) => callback(request);
    ipcRenderer.on('kyrozen:confirmation-request', handler);
    return () => ipcRenderer.removeListener('kyrozen:confirmation-request', handler);
  },
  respondConfirmation: (confirmationId: string, confirmed: boolean, trustForSession = false, storeId?: string | null) =>
    ipcRenderer.invoke('kyrozen:respond-confirmation', confirmationId, confirmed, trustForSession, storeId),

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

  onGitHubStatus: (callback: (status: { connected: boolean; scope?: string; login?: string; avatarUrl?: string; expired?: boolean }) => void) => {
    const handler = (_event: unknown, status: { connected: boolean; scope?: string; login?: string; avatarUrl?: string; expired?: boolean }) => callback(status);
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
  onHardwareToolStatus: (callback: (tools: Record<string, unknown>) => void) => {
    const handler = (_event: unknown, tools: Record<string, unknown>) => callback(tools);
    ipcRenderer.on('kyrozen:hardware-tool-status', handler);
    return () => ipcRenderer.removeListener('kyrozen:hardware-tool-status', handler);
  },
  connectGitHub: () => ipcRenderer.invoke('kyrozen:connect-github'),
  startGithubLogin: () => ipcRenderer.invoke('kyrozen:start-github-login'),
  getGitHubStatus: () => ipcRenderer.invoke('kyrozen:get-github-status'),
  disconnectGitHub: () => ipcRenderer.invoke('kyrozen:disconnect-github'),
  createGitHubRepo: (owner: string, name: string, description?: string, isPrivate?: boolean) =>
    ipcRenderer.invoke('kyrozen:create-github-repo', owner, name, description, isPrivate),
  getGitCommits: (projectId?: string) => ipcRenderer.invoke('kyrozen:get-git-commits', projectId || ''),
  initGitRepo: (remoteUrl?: string) => ipcRenderer.invoke('kyrozen:init-git-repo', remoteUrl),
  getGitStatus: (projectId?: string) => ipcRenderer.invoke('kyrozen:get-git-status', projectId || ''),
  commitAndPush: (message: string) => ipcRenderer.invoke('kyrozen:commit-and-push', message),
  generateCommitMessage: (projectId?: string) => ipcRenderer.invoke('kyrozen:generate-commit-message', projectId || ''),

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
