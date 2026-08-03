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

// Stage gate (feature 3.2): real progress + per-condition gate status.
export interface StageCondition {
  item_id: string;
  label: string;
  kind: 'deliverable' | 'confirmation' | 'verification' | 'task';
  satisfied: boolean;
  skippable: boolean;
  skipped: boolean;
  detail: string;
  required: boolean;
}

export interface StageGate {
  stage: string;
  stage_label: string;
  index: number;
  total: number;
  satisfied: StageCondition[];
  missing: StageCondition[];
  can_advance: boolean;
  blocked_entry_reason: string | null;
  failed_tasks: Array<{ task_id: string; error: string; repair: string }>;
  progress: number;
}

export interface StageSkip {
  item_id: string;
  reason: string;
  impact: string;
  approver: string;
  recovery: string;
  at: number;
}

export interface StageGateStatus {
  task_id?: string;
  stage: string;
  progress: number;
  gate: StageGate;
  skips: StageSkip[];
}

// Feature 3.3: real software generation / run / repair (SoftwareFeatureTool).
export interface FeatureRecord {
  prd_feature: string;
  files: string[];
  tests: string[];
  status: string;
  notes: string;
}

// P0-R6: real execution planning, persisted to .kyrozen/PLAN.json.
export interface PlanStepPayload {
  id: string;
  title?: string;
  detail?: string;
  status?: 'pending' | 'in_progress' | 'completed' | 'failed' | string;
}

export interface PlanPayload {
  task_id?: string;
  stage?: string;
  title?: string;
  goal?: string;
  steps?: PlanStepPayload[];
}

export interface SoftwareRunResult {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  cwd: string;
}

export interface SoftwareRepairStep {
  task_path: string;
  error_summary: string;
  fix_applied: string;
  file: string;
}

export interface SoftwareRepairOutcome {
  success: boolean;
  attempts: number;
  final_result: SoftwareRunResult | null;
  repairs: SoftwareRepairStep[];
  associated_task: string;
}

export interface SoftwareRunSummary {
  install: SoftwareRunResult | null;
  build: SoftwareRunResult | null;
  test: SoftwareRunResult | null;
  core_flow: SoftwareRunResult | null;
  preview_url: string;
  command: string;
  artifact_path: string;
  overall_success: boolean;
  feature_records: FeatureRecord[];
  fix_count: number;
}

export interface SoftwareFeatureResult {
  action: 'generate' | 'run' | 'repair' | 'noncoding';
  app_type?: string;
  files?: string[];
  manifest_path?: string;
  feature_slugs?: string[];
  run?: SoftwareRunSummary;
  feature_records?: FeatureRecord[];
  preview_url?: string;
  command?: string;
  artifact_path?: string;
  saved_path?: string;
  repair?: SoftwareRepairOutcome;
  deliverable_type?: string;
  title?: string;
  file?: string;
  markdown?: string;
}

// Feature 3.4: attachments, status bar, operation log, confirmations.
export interface AttachmentInfo {
  id: string;
  kind: 'image' | 'video' | 'other';
  filename: string;
  path: string;
  size_bytes: number;
  mime: string;
  thumbnail_path: string | null;
  analysis: Record<string, unknown> | null;
  error: string | null;
}

export interface OperationLogEntry {
  id: string;
  action: string;
  started_at: number;
  ended_at: number | null;
  duration_ms: number | null;
  input_summary: string;
  output_summary: string;
  status: string;
  error_reason: string;
}

export interface InteractionStatus {
  state: string | null;
  detail: string | null;
  since: number | null;
}

export interface PendingConfirmationInfo {
  id: string;
  operation_type: string;
  action_label: string;
  params: Record<string, unknown>;
  reason: string;
  status: string;
  restored?: boolean;
}

export interface KyrozenAPI {
  login: (email: string, password: string, serverUrl: string) => Promise<LoginResult>;
  verifyOpenToken: (token: string) => Promise<VerifyResult | null>;
  loadChatMessages: (projectId: string) => Promise<{ success: boolean; messages: Array<{ id: string; role: string; content: string; metadata?: Record<string, unknown>; created_at?: string }>; error?: string }>;
  setCurrentProject: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  pickWorkspace: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  getWorkspaceRoot: (projectId: string) => Promise<{ workspaceRoot: string | null }>;
  getProjects: () => Promise<Array<{ id: string; name: string; current_stage: string; description?: string; local_only?: boolean }>>;
  createProject: (name: string, description?: string, goal?: string) => Promise<{ success: boolean; project?: { id: string; name: string; current_stage: string }; error?: string }>;
  renameProject: (projectId: string, name: string) => Promise<{ success: boolean; project?: { id: string; name: string }; error?: string }>;
  openProjectInFinder: (projectId: string) => Promise<{ success: boolean; workspaceRoot?: string; error?: string }>;
  deleteProject: (projectId: string) => Promise<{ success: boolean; projectId?: string; localWorkspaceDeleted?: boolean; error?: string }>;
  getProjectState: (projectId: string) => Promise<{ project_id: string; project_type?: 'software' | 'embedded' | 'hybrid'; workflow_version?: string; workflow_stages?: string[]; stage: string; progress: number; blocked_reason: string | null; next_action: { action: string; reason: string; target_mode: string } | null } | null>;
  getProjectWorkspace: (projectId: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createArtifact: (projectId: string, type: string, title: string, content: string, changeReason?: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createEvidence: (projectId: string, evidence: Record<string, unknown>) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  runResearch: (projectId: string, query: string, limit?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  evidenceImpact: (projectId: string, artifactId: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  deleteEvidence: (projectId: string, artifactId: string, expectedVersion?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  editEvidence: (projectId: string, artifactId: string, evidence: Record<string, unknown>, expectedVersion?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  updateEvidence: (projectId: string, artifactId: string, status: 'active' | 'invalid' | 'deleted', expectedVersion?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  mergeEvidence: (projectId: string, artifactId: string, targetEvidenceId: string, expectedSourceVersion?: number, expectedTargetVersion?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  getSolutions: (projectId: string) => Promise<{ success: boolean; data?: { comparison?: Record<string, unknown>; confirmed?: boolean; validation_errors?: string[] }; error?: string }>;
  saveSolution: (projectId: string, comparison: Record<string, unknown>, action: string, affectedTasks?: string[]) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  confirmProtocol: (projectId: string, protocol: Record<string, unknown>, confirmed?: boolean, affectedFiles?: string[], affectedTasks?: string[]) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  confirmWorkflow: (projectId: string, projectType: 'software' | 'embedded' | 'hybrid') => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  advanceHybridTrack: (projectId: string, track: string, expectedVersion?: number) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  runLocalHardware: (projectId: string, workspaceRoot: string, action: string, options?: { board?: string; port?: string; baud?: number; transport?: string; message?: Record<string, unknown> }) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  runProtocolScenarios: (projectId: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createDecision: (projectId: string, decision: string, reason: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  createFeedback: (projectId: string, description: string, type: string, priority: string, validation?: Record<string, unknown>) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  updateSuggestionStatus: (projectId: string, suggestionId: string, status: string) => Promise<{ success: boolean; data?: Record<string, unknown>; error?: string }>;
  deleteLearningItem: (projectId: string, kind: string, itemId: string) => Promise<{ success: boolean; error?: string }>;
  exportProject: (projectId: string) => Promise<{ success: boolean; cancelled?: boolean; filePath?: string; error?: string }>;
  getQuota: () => Promise<{
    allowed: boolean;
    reason: string;
    used: number;
    limit: number;
    remaining: number;
    plan?: 'free' | 'lite' | 'pro' | 'ultimate' | 'enterprise' | 'developer';
    project_limit?: number;
    weekly_credit_limit?: number;
    rolling_credits?: number;
    rolling_limit?: number;
    monthly_cost_rmb?: number;
    monthly_cost_limit_rmb?: number;
    conversations?: number;
    conversation_limit?: number;
    weekly_reset_at?: string;
    rolling_reset_at?: string;
    period_end?: string;
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
  startAfdianConnect: () => Promise<{ authorize_url?: string; state?: string; error?: string }>;
  startAfdianCheckout: (plan: 'lite' | 'pro' | 'ultimate') => Promise<{ id?: string; checkout_url?: string; status?: string; error?: string }>;
  getAfdianPaymentStatus: (checkoutId: string) => Promise<{ status?: string; error?: string }>;
  onSessionResumed: (callback: (token: string, serverUrl: string) => void) => () => void;
  onLoginFailed: (callback: (message: string) => void) => () => void;
  onSessionEnded: (callback: () => void) => () => void;
  onSessionExpired: (callback: (message: string) => void) => () => void;
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
  onChatMessage: (callback: (message: { role: string; content: string; raw?: string; error?: string; operations?: Array<{ description: string; status: string; timestamp: string }> }) => void) => () => void;
  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) => () => void;
  onPlanUpdated: (callback: (payload: { task_id: string; plan: PlanPayload; source: string }) => void) => () => void;
  readWorkspacePlan: (workspaceRoot: string) => Promise<{ success: boolean; plan: PlanPayload | null; error?: string }>;
  onTaskActivity: (callback: (activity: { task_id: string; description: string; status: string }) => void) => () => void;
  onAgentRouted: (callback: (decision: { task_id: string; mode: string; mode_label: string; agent_name: string; agent_display_name: string; reason: string; available_tools: string[]; restricted_tools: string[]; degraded: boolean }) => void) => () => void;
  onAgentDegraded: (callback: (info: { task_id: string; agent_display_name: string; reason: string; repair_steps: string[] }) => void) => () => void;
  onStageUpdated: (callback: (status: StageGateStatus) => void) => () => void;
  onAgentReady: (callback: (info: { status: 'ready' | 'down'; version?: string; mode?: string; code?: number | null; retrying?: boolean }) => void) => () => void;
  onSoftwareFeature: (callback: (result: SoftwareFeatureResult) => void) => () => void;
  sendSoftwareFeature: (params: Record<string, unknown>) => void;
  sendStageAction: (action: 'refresh' | 'advance_normal' | 'return', stage: string) => Promise<{ ok: boolean }>;
  onConfirmationRequest: (callback: (request: { confirmation_id: string; store_id?: string | null; task_id: string; tool: string; action: string; parameters: Record<string, unknown>; reason: string; detail: string; choices?: string[] }) => void) => () => void;
  respondConfirmation: (confirmationId: string, confirmed: boolean, trustForSession?: boolean, storeId?: string | null) => Promise<{ success: boolean; error?: string }>;
  onStatusUpdated: (callback: (status: InteractionStatus) => void) => () => void;
  onInteraction: (callback: (payload: Record<string, unknown>) => void) => () => void;
  sendInteraction: (params: Record<string, unknown>) => void;
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
  disconnectGitHub: () => Promise<{ success: boolean }>;
  createGitHubRepo: (owner: string, name: string, description?: string, isPrivate?: boolean) => Promise<{
    success: boolean;
    url?: string;
    cloneUrl?: string;
    owner?: string;
    failureKind?: string;
    reason?: string;
    recovery?: string;
    error?: string;
  }>;
  getGitHubStatus: () => Promise<{ connected: boolean; scope?: string; login?: string; avatarUrl?: string; expired?: boolean }>;
  initGitRepo: (remoteUrl?: string) => Promise<{ success: boolean; error?: string }>;
  getGitStatus: (projectId?: string) => Promise<{
    success: boolean;
    isRepo: boolean;
    branch?: string;
    ahead?: number;
    behind?: number;
    modified?: string[];
    untracked?: string[];
    staged?: string[];
    recentCommits?: Array<{ hash: string; message: string; date: string; author: string }>;
    remoteUrl?: string | null;
    error?: string;
  }>;
  getGitCommits: (projectId?: string) => Promise<{ success: boolean; commits: Array<{ hash: string; message: string; date: string; author: string; files?: string[] }>; remoteUrl: string | null; error?: string }>;
  commitAndPush: (message: string) => Promise<{
    success: boolean;
    committed?: boolean;
    failureKind?: string;
    reason?: string;
    recovery?: string;
    error?: string;
  }>;
  generateCommitMessage: (projectId?: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  onGitHubStatus: (callback: (status: { connected: boolean; scope?: string; login?: string; avatarUrl?: string; expired?: boolean }) => void) => () => void;
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
