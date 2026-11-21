import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { http, setUnauthorizedHandler, tokenStore } from "@/api/client";
import type { TokenResponse, User } from "@/api/types";
import { supabase } from "@/lib/supabase";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!tokenStore.get());

  const logout = useCallback(() => {
    supabase.auth.signOut().catch(() => {});
    tokenStore.clear();
    setUser(null);
    qc.clear(); // never leak one user's cached data to the next
  }, [qc]);

  useEffect(() => { setUnauthorizedHandler(logout); }, [logout]);

  const exchangeSupabaseToken = useCallback(async (accessToken: string) => {
    try {
      const res = await http.post<TokenResponse>("/auth/google", { access_token: accessToken });
      tokenStore.set(res.access_token);
      setUser(res.user);
    } catch {
      tokenStore.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Check for an existing Supabase session on mount (handles OAuth redirect case)
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token && !tokenStore.get()) {
        // Google OAuth just landed — exchange for TestPilot JWT
        exchangeSupabaseToken(session.access_token);
      } else if (tokenStore.get()) {
        // Already have a TestPilot token — verify it
        http.get<User>("/auth/me").then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false));
      } else {
        setLoading(false);
      }
    });

    // Also listen for future auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session?.access_token && !tokenStore.get()) {
        exchangeSupabaseToken(session.access_token);
      }
    });

    return () => { subscription.unsubscribe(); };
  }, [exchangeSupabaseToken]);
  const accept = (res: TokenResponse) => { tokenStore.set(res.access_token); setUser(res.user); };
  const value = useMemo<AuthState>(() => ({
    user, loading, logout,
    login: async (email, password) => accept(await http.post<TokenResponse>("/auth/login", { email, password })),
    register: async (email, password, full_name) => accept(await http.post<TokenResponse>("/auth/register", { email, password, full_name })),
  }), [user, loading, logout]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
