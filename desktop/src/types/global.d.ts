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

  requestInitialToken: () => void;
  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) => void;
  onProtocolUrl: (callback: (url: string) => void) => void;
  sendChat: (message: string) => void;
  cancelTask: () => void;
  onChatMessage: (callback: (message: { role: string; content: string }) => void) => void;
  onExecutionPlan: (callback: (plan: { task_id: string; steps: string[] }) => void) => void;
  checkForUpdates: () => Promise<{ success: boolean; error?: string }>;
  onUpdateStatus: (callback: (status: { status: string; message: string }) => void) => void;
  ensureHardwareToolchain: () => Promise<{
    success: boolean;
    arduino?: { path: string | null; version: string | null };
    pio?: { path: string | null; version: string | null };
    error?: string;
  }>;
  installCommonCores: () => Promise<{ success: boolean; error?: string }>;
  connectGitHub: () => Promise<{ success: boolean; error?: string }>;
}

declare global {
  interface Window {
    kyrozen?: KyrozenAPI;
  }
}

export {};
