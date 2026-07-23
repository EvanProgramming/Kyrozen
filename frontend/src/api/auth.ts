import { apiClient } from './client';
import type { AuthResponse, LoginCredentials, RegisterCredentials, User } from '../types/api';

export async function register(credentials: RegisterCredentials): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>('/auth/signup', {
    email: credentials.email,
    password: credentials.password,
    name: credentials.name || credentials.email.split('@')[0],
  });
  return data;
}

export async function login(credentials: LoginCredentials): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>('/auth/signin', credentials);
  return data;
}

export async function logout(): Promise<void> {
  // Tokens are kept in memory only; clearing local state is sufficient.
  return Promise.resolve();
}

export async function fetchCurrentUser(): Promise<User> {
  const response = await apiClient.get<User>('/auth/me');
  return response.data;
}
