'use client';

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { useRouter } from 'next/navigation';
import {
  type AuthUser,
  type AuthResponse,
  saveAuth,
  clearAuth,
  getToken,
  getCachedUser,
  apiMe,
  apiLogin,
  apiRegister,
} from '@/lib/auth';

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount: hydrate from localStorage, then verify with /auth/me
  useEffect(() => {
    const stored = getToken();
    const cached = getCachedUser();
    if (stored && cached) {
      setToken(stored);
      setUser(cached);
      // Verify in background
      apiMe(stored)
        .then((freshUser) => setUser(freshUser))
        .catch(() => {
          clearAuth();
          setToken(null);
          setUser(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const _applyAuth = useCallback((res: AuthResponse) => {
    saveAuth(res);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await apiLogin(email, password);
      _applyAuth(res);
      router.push('/dashboard');
    },
    [_applyAuth, router],
  );

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await apiRegister(email, password, name);
      _applyAuth(res);
      router.push('/dashboard');
    },
    [_applyAuth, router],
  );

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
    router.push('/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
