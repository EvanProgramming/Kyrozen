import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { apiClient } from './client';
import type { AuthResponse, LoginCredentials, RegisterCredentials, User } from '../types/api';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export async function register(credentials: RegisterCredentials): Promise<AuthResponse> {
  const { data, error } = await supabase.auth.signUp({
    email: credentials.email,
    password: credentials.password,
    options: {
      data: {
        name: credentials.name || credentials.email.split('@')[0],
      },
    },
  });

  if (error) {
    throw new Error(error.message);
  }

  if (!data.session || !data.user) {
    throw new Error('Registration did not return a session');
  }

  const user: User = {
    user_id: data.user.id,
    email: data.user.email || credentials.email,
    name: data.user.user_metadata?.name || null,
    role: data.user.user_metadata?.role || 'user',
    created_at: data.user.created_at || new Date().toISOString(),
  };

  return {
    user,
    access_token: data.session.access_token,
    refresh_token: data.session.refresh_token,
  };
}

export async function login(credentials: LoginCredentials): Promise<AuthResponse> {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: credentials.email,
    password: credentials.password,
  });

  if (error) {
    throw new Error(error.message);
  }

  if (!data.session || !data.user) {
    throw new Error('Login did not return a session');
  }

  const user: User = {
    user_id: data.user.id,
    email: data.user.email || credentials.email,
    name: data.user.user_metadata?.name || null,
    role: data.user.user_metadata?.role || 'user',
    created_at: data.user.created_at || new Date().toISOString(),
  };

  return {
    user,
    access_token: data.session.access_token,
    refresh_token: data.session.refresh_token,
  };
}

export async function logout(): Promise<void> {
  await supabase.auth.signOut();
}

export async function fetchCurrentUser(): Promise<User> {
  const response = await apiClient.get<User>('/auth/me');
  return response.data;
}
