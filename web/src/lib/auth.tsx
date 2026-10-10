import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, onUnauthorized } from "./api";

export interface User {
  user_id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
}

type LoginResult = { mfaToken: string } | { user: User };

interface AuthState {
  user: User | null;
  /** True until the first /me check finishes, so routes don't flash the login page. */
  loading: boolean;
  /** Set when a session ended on its own (timeout/revocation) rather than by the user. */
  expired: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  loginMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    api<User>("/auth/me", { silent401: true })
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(
    () =>
      onUnauthorized(() => {
        setUser((current) => {
          if (current) setExpired(true);
          return null;
        });
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const res = await api<{ mfa_required: boolean; mfa_token?: string; user?: User }>("/auth/login", {
      json: { email, password },
      silent401: true,
    });
    if (res.mfa_required && res.mfa_token) return { mfaToken: res.mfa_token };
    setExpired(false);
    setUser(res.user!);
    return { user: res.user! };
  }, []);

  const loginMfa = useCallback(async (mfaToken: string, code: string) => {
    const res = await api<{ user: User }>("/auth/login/mfa", {
      json: { mfa_token: mfaToken, code },
      silent401: true,
    });
    setExpired(false);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", silent401: true });
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    setExpired(false);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, expired, login, loginMfa, logout }),
    [user, loading, expired, login, loginMfa, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
