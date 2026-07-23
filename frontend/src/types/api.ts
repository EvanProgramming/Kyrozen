export interface User {
  user_id: string;
  email: string;
  name: string | null;
  role: 'user' | 'admin' | 'beta';
  created_at: string;
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string;
  goal: string;
  status: 'active' | 'paused' | 'completed' | 'archived';
  current_stage: string;
  next_steps: string;
  blocked_reason: string | null;
  progress: number;
  risks: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  goal?: string;
}

export interface ProjectState {
  project_id: string;
  stage: string;
  progress: number;
  blocked_reason: string | null;
  next_action: {
    action: string;
    reason: string;
    target_mode: string;
  } | null;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  name?: string;
}

export interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

export interface ApiError {
  detail: string;
}

export interface ChatRequest {
  message: string;
  project_id?: string;
  mode?: string;
  confirmed?: boolean;
}

export interface ChatResponse {
  task_id: string;
  status: string;
  project_id?: string;
  mode?: string;
}

export interface ChatMessage {
  id: string;
  user_id: string;
  project_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface TaskStep {
  description: string;
  status: string;
  metadata?: Record<string, unknown>;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: string;
  project_id?: string;
  result?: unknown;
  errors: string[];
  steps: TaskStep[];
}
