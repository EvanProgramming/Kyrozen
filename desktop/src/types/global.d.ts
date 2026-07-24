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
  requestInitialToken: () => void;
  onConnectionChange: (callback: (state: ConnectionState, message: string) => void) => void;
  onProtocolUrl: (callback: (url: string) => void) => void;
  sendChat: (message: string) => void;
  cancelTask: () => void;
  onChatMessage: (callback: (message: { role: string; content: string }) => void) => void;
}

declare global {
  interface Window {
    kyrozen?: KyrozenAPI;
  }
}

export {};
