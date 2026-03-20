const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: 'user' | 'admin';
  profile: 'team_member' | 'founder' | 'editor' | 'manager' | 'analyst';
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

// ── Token storage ──────────────────────────────────────────────────────────

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

export function saveAuth(res: AuthResponse) {
  localStorage.setItem(TOKEN_KEY, res.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(res.user));
  // Also set a cookie so Next.js middleware can read it
  document.cookie = `auth_token=${res.access_token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  document.cookie = 'auth_token=; path=/; max-age=0';
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getCachedUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

// ── API calls ──────────────────────────────────────────────────────────────

export async function apiRegister(
  email: string,
  password: string,
  name: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? 'Registration failed');
  return data as AuthResponse;
}

export async function apiLogin(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? 'Login failed');
  return data as AuthResponse;
}

export async function apiMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Session expired');
  return res.json() as Promise<AuthUser>;
}

export async function apiListUsers(token: string): Promise<(AuthUser & { created_at: string })[]> {
  const res = await fetch(`${API}/auth/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to load users');
  return res.json();
}

export async function apiUpdateUser(
  token: string,
  userId: string,
  update: { role?: string; profile?: string; name?: string },
): Promise<AuthUser> {
  const res = await fetch(`${API}/auth/users/${userId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(update),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? 'Update failed');
  return data as AuthUser;
}
