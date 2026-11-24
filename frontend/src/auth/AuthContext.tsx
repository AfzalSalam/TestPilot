import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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

  // Check if landing from Google OAuth redirect (URL contains #access_token)
  const isOAuthRedirect = typeof window !== "undefined" && window.location.hash.includes("access_token");

  // Initial loading state: true if we have a token stored or are landing from OAuth redirect
  const [loading, setLoading] = useState<boolean>(!!tokenStore.get() || isOAuthRedirect);

  // Prevent multiple calls to /auth/google for the same token or concurrently
  const exchangingRef = useRef(false);
  const handledTokensRef = useRef<Set<string>>(new Set());

  const logout = useCallback(() => {
    supabase.auth.signOut().catch(() => {});
    tokenStore.clear();
    setUser(null);
    qc.clear(); // never leak one user's cached data to the next
  }, [qc]);

  useEffect(() => { setUnauthorizedHandler(logout); }, [logout]);

  const exchangeSupabaseToken = useCallback(async (accessToken: string) => {
    if (!accessToken || handledTokensRef.current.has(accessToken) || exchangingRef.current) {
      return;
    }
    handledTokensRef.current.add(accessToken);
    exchangingRef.current = true;
    setLoading(true);

    // Clean hash from URL so reloads/navigation don't re-trigger OAuth processing
    if (window.location.hash && window.location.hash.includes("access_token")) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }

    try {
      const res = await http.post<TokenResponse>("/auth/google", { access_token: accessToken });
      tokenStore.set(res.access_token);
      setUser(res.user);
      // Supabase OAuth succeeded; sign out Supabase client to prevent duplicate events & auto-refresh
      supabase.auth.signOut().catch(() => {});
    } catch (err) {
      handledTokensRef.current.delete(accessToken);
      tokenStore.clear();
      setUser(null);
      console.error("Google sign-in exchange failed:", err);
    } finally {
      setLoading(false);
      exchangingRef.current = false;
    }
  }, []);

  useEffect(() => {
    // Listen for Supabase auth state changes (OAuth redirect initial session)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token && !tokenStore.get()) {
        exchangeSupabaseToken(session.access_token);
      } else if (!session && !tokenStore.get()) {
        setLoading(false);
      }
    });

    // If we already have a TestPilot token, verify it
    if (tokenStore.get()) {
      http.get<User>("/auth/me").then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false));
    }

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
