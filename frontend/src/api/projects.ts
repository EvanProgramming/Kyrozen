import { apiClient } from './client';
import type { CreateProjectRequest, Evidence, Phase2Workbench, Project, ProjectState } from '../types/api';

export async function listProjects(): Promise<Project[]> {
  const response = await apiClient.get<Project[]>('/projects');
  return response.data;
}

export async function createProject(request: CreateProjectRequest): Promise<Project> {
  const response = await apiClient.post<Project>('/projects', request);
  return response.data;
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await apiClient.get<Project>(`/projects/${projectId}`);
  return response.data;
}

export async function updateProject(
  projectId: string,
  updates: Partial<Project>
): Promise<Project> {
  const response = await apiClient.put<Project>(`/projects/${projectId}`, updates);
  return response.data;
}

export async function renameProject(projectId: string, name: string): Promise<Project> {
  const response = await apiClient.put<Project>(`/projects/${projectId}`, { name });
  return response.data;
}

export async function archiveProject(projectId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/projects/${projectId}/archive`, {});
  return response.data;
}

export async function restoreProject(projectId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/projects/${projectId}/restore`, {});
  return response.data;
}

export async function deleteProject(projectId: string): Promise<{ status: string; project_id: string }> {
  const response = await apiClient.delete<{ status: string; project_id: string }>(`/projects/${projectId}`);
  return response.data;
}

export async function getProjectState(projectId: string): Promise<ProjectState> {
  const response = await apiClient.get<ProjectState>(`/projects/${projectId}/state`);
  return response.data;
}

export async function advanceProjectStage(projectId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/projects/${projectId}/advance`, {});
  return response.data;
}

export async function getPhase2Workbench(projectId: string): Promise<Phase2Workbench> {
  const response = await apiClient.get<Phase2Workbench>(`/projects/${projectId}/phase2/workbench`);
  return response.data;
}

export async function createEvidence(projectId: string, evidence: Omit<Evidence, 'artifact_id' | 'version' | 'title' | 'observed_at' | 'status'>): Promise<Evidence> {
  const response = await apiClient.post<Evidence>(`/projects/${projectId}/evidence`, evidence);
  return response.data;
}
