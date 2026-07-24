import { apiClient } from './client';
import type { ChatMessage, ChatRequest, ChatResponse, Task } from '../types/api';

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  // Market research and other agent loops can take longer than the default 60s timeout.
  const response = await apiClient.post<ChatResponse>('/chat', request, { timeout: 300000 });
  return response.data;
}

export async function getChatHistory(projectId: string): Promise<ChatMessage[]> {
  const response = await apiClient.get<ChatMessage[]>(`/projects/${projectId}/chat`);
  return response.data;
}

export async function getTask(taskId: string): Promise<Task> {
  const response = await apiClient.get<Task>(`/tasks/${taskId}`);
  return response.data;
}

export async function confirmTask(taskId: string, confirmed: boolean): Promise<Task> {
  const response = await apiClient.post<Task>(`/tasks/${taskId}/confirm`, { confirmed });
  return response.data;
}
