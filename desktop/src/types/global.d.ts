import { ConnectionState } from '../App';

export interface LoginResult {
  success: boolean;
  wsToken?: string;
  error?: string;
}

export interface VerifyResult {
  wsToken: string;
  refreshToken: string;
}

export interface KyrozenAPI {
  login: (email: string, password: string, serverUrl: string) => Promise<LoginResult>;
  verifyOpenToken: (token: string) => Promise<VerifyResult | null>;
  setCurrentProject: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  pickWorkspace: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  getWorkspaceRoot: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  getProjects: () => Promise<Array<{ id: string; name: string; current_stage: string; description?: string }>>;
  createProject: (name: string, description?: string, goal?: string) => Promise<{ success: boolean; project?: { id: string; name: string; current_stage: string }; error?: string }>;
  getProjectState: (projectId: string) => Promise<{ project_id: string; stage: string; progress: number; blocked_reason: string | null; next_action: { action: string; reason: string; target_mode: string } | null } | null>;
  getProjectWorkspace: (projectId: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createDecision: (projectId: string, decision: string, reason: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createFeedback: (projectId: string, description: string, type: string, priority: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  updateSuggestionStatus: (projectId: string, suggestionId: string, status: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  deleteLearningItem: (projectId: string, kind: string, itemId: string) => Promise<{ success: boolean; error?: string }>;
  exportProject: (projectId: string) => Promise<{ success: boolean; cancelled?: boolean; filePath?: string; error?: string }>;
  getQuota: () => Promise<{
    allowed: boolean;
    reason: string;
    used: number;
    limit: number;
    remaining: number;
    plan?: 'free' | 'developer';
    project_limit?: number;
  }>;
  getServerUrl: () => Promise<string>;
  setServerUrl: (url: string) => Promise<{ success: boolean; serverUrl?: string; error?: string }>;
  getFullTrust: () => Promise<{ enabled: boolean }>;
  setFullTrust: (enabled: boolean) => Promise<{ enabled: boolean }>;

  listFiles: (projectId: string) => Promise<{ files: string[]; error?: string }>;
  readFile: (projectId: string, relativePath: string) => Promise<{ content: string; error?: string }>;
  saveFile: (projectId: string, relativePath: string, content: string) => Promise<{ success: boolean; error?: string }>;
  searchAcrossProjects: (
    query: string,
    options?: { maxResults?: number; includeContent?: boolean }
  ) => Promise<{
    results: Array<{ projectId: string; relativePath: string; matchType: 'filename' | 'content'; snippet?: string }>;
    error?: string;
  }>;

  requestInitialToken: () => void;
  getInitialSession: () => Promise<{ wsToken: string | null; serverUrl: string; currentProjectId: string | null; connection: ConnectionState; message: string }>;
  getUserProfile: () => Promise<{ name: string; email: string; githubUsername: string; avatarUrl: string }>;
  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) => () => void;
  onProtocolUrl: (callback: (url: string) => void) => () => void;
  onSessionResumed: (callback: (token: string, serverUrl: string) => void) => () => void;
  onSessionEnded: (callback: () => void) => () => void;
  onOpenSettings: (callback: () => void) => () => void;
  sendChat: (message: string) => Promise<{
    success: boolean;
    taskId?: string;
    dispatched?: boolean;
    error?: string;
    content?: string;
    operations?: Array<{ description: string; status: string; timestamp: string }>;
  }>;
  cancelTask: () => void;
  startPairing: (serverUrl: string) => Promise<{ success: boolean; code?: string; expiresIn?: number; error?: string }>;
  pollPairing: (serverUrl: string, code: string) => Promise<{ success: boolean; ready?: boolean; wsToken?: string; error?: string }>;
  onChatMessage: (callback: (message: { role: string; content: string; raw?: string; operations?: Array<{ description: string; status: string; timestamp: string }> }) => void) => () => void;
  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) => () => void;
  onTaskActivity: (callback: (activity: { task_id: string; description: string; status: string }) => void) => () => void;
  onAgentRouted: (callback: (decision: { task_id: string; mode: string; mode_label: string; agent_name: string; agent_display_name: string; reason: string; available_tools: string[]; restricted_tools: string[]; degraded: boolean }) => void) => () => void;
  onAgentDegraded: (callback: (info: { task_id: string; agent_display_name: string; reason: string; repair_steps: string[] }) => void) => () => void;
  onConfirmationRequest: (callback: (request: { confirmation_id: string; task_id: string; tool: string; action: string; parameters: Record<string, unknown>; reason: string; detail: string }) => void) => () => void;
  respondConfirmation: (confirmationId: string, confirmed: boolean, trustForSession?: boolean) => Promise<{ success: boolean; error?: string }>;
  openPreview: (url: string, mode: 'embedded' | 'window' | 'external') => Promise<{ success: boolean; error?: string }>;
  onOpenPreviewUrl: (callback: (url: string) => void) => () => void;

  checkForUpdates: () => Promise<{ success: boolean; error?: string }>;
  onUpdateStatus: (callback: (status: { status: string; message: string }) => void) => () => void;
  ensureHardwareToolchain: () => Promise<{
    success: boolean;
    arduino?: { path: string | null; version: string | null };
    pio?: { path: string | null; version: string | null };
    error?: string;
  }>;
  installCommonCores: () => Promise<{ success: boolean; error?: string }>;
  checkHardwareUpdates: () => Promise<{
    success: boolean;
    results?: Array<{
      tool: string;
      currentVersion: string | null;
      latestVersion: string | null;
      updated: boolean;
      error?: string;
    }>;
    error?: string;
  }>;
  getHardwareToolStatus: () => Promise<{
    success: boolean;
    tools: Record<string, { command: string; path: string | null; bundled: boolean; version: string | null }>;
  }>;
  onHardwareToolStatus: (callback: (tools: Record<string, { command: string; path: string | null; bundled: boolean; version: string | null }>) => void) => () => void;
  connectGitHub: () => Promise<{ success: boolean; error?: string }>;
  startGithubLogin: () => Promise<{ success: boolean; error?: string }>;
  createGitHubRepo: (name: string, description?: string, isPrivate?: boolean) => Promise<{ success: boolean; url?: string; cloneUrl?: string; error?: string }>;
  getGitHubStatus: () => Promise<{ connected: boolean; scope?: string }>;
  initGitRepo: (remoteUrl?: string) => Promise<{ success: boolean; error?: string }>;
  getGitStatus: () => Promise<{
    success: boolean;
    isRepo: boolean;
    branch?: string;
    ahead?: number;
    behind?: number;
    modified?: string[];
    untracked?: string[];
    error?: string;
  }>;
  commitAndPush: (message: string) => Promise<{ success: boolean; error?: string }>;
  setAutoCommit: (enabled: boolean) => Promise<{ success: boolean; error?: string }>;
  getAutoCommit: () => Promise<{ enabled: boolean }>;
  onGitHubStatus: (callback: (status: { connected: boolean; scope?: string }) => void) => () => void;
  onFullTrustChange: (callback: (status: { enabled: boolean }) => void) => () => void;

  getOnboardingStatus: () => Promise<{ completed: boolean; language: 'zh' | 'en'; completedAt?: string }>;
  getOnboardingLanguage: () => Promise<{ language: 'zh' | 'en' }>;
  saveOnboardingLanguage: (language: 'zh' | 'en') => Promise<{ language: 'zh' | 'en' }>;
  completeOnboarding: (language?: 'zh' | 'en') => Promise<{ completed: boolean; language: 'zh' | 'en' }>;

  logout: () => Promise<{ success: boolean }>;
  checkPythonRuntime: () => Promise<{ ready: boolean; path: string | null; error?: string }>;
  ensurePythonRuntime: () => Promise<{ success: boolean; path: string | null; error?: string }>;
  ensureProjectVenv: () => Promise<{ success: boolean; pythonPath: string | null; created?: boolean; error?: string }>;
  installProjectDeps: (packages?: string[]) => Promise<{ success: boolean; installed: string[]; error?: string }>;
  getProjectVenv: () => Promise<{ ready: boolean; pythonPath: string | null }>;
  pickOnboardingWorkspace: () => Promise<{ workspaceRoot: string | null }>;
  importLocalProject: () => Promise<{ projectId: string; name: string; workspaceRoot: string } | null>;

  onOnboardingProgress: (callback: (progress: { step: string; message: string }) => void) => () => void;
}

declare global {
  interface Window {
    kyrozen?: KyrozenAPI;
  }
}

export {};
