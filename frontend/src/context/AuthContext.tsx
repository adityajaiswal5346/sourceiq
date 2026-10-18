/**
 * DocuMind — AuthContext
 * Google credential stored in memory only — never localStorage.
 * Typed with strict interfaces. No `any`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../types/api";

// ── Types ──────────────────────────────────────────────────────────

interface AuthState {
  readonly user:       User | null;
  readonly credential: string | null;
  readonly loading:    boolean;
}

interface AuthActions {
  signInWithGoogle: (googleCredential: string) => Promise<void>;
  signOut:          () => void;
  refreshUser:      () => Promise<void>;
}

type AuthContextValue = AuthState & AuthActions;

// ── Context ────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be called within <AuthProvider />");
  }
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────

const INITIAL_STATE: AuthState = {
  user:       null,
  credential: null,
  loading:    false,
};

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [state, setState] = useState<AuthState>(INITIAL_STATE);

  const signInWithGoogle = useCallback(async (googleCredential: string): Promise<void> => {
    setState(prev => ({ ...prev, loading: true }));
    try {
      const user = await api.auth.google(googleCredential);
      setState({ user, credential: googleCredential, loading: false });
    } catch (error) {
      setState(prev => ({ ...prev, loading: false }));
      throw error instanceof ApiError
        ? error
        : new Error("Sign-in failed. Please try again.");
    }
  }, []);

  const signOut = useCallback((): void => {
    setState(INITIAL_STATE);
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    if (!state.credential) return;
    try {
      const user = await api.auth.me(state.credential);
      setState(prev => ({ ...prev, user }));
    } catch (error) {
      if (error instanceof ApiError && error.statusCode === 401) {
        // Token expired — force re-authentication
        setState(INITIAL_STATE);
      }
      // Other errors are non-fatal — keep current state
    }
  }, [state.credential]);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, signInWithGoogle, signOut, refreshUser }),
    [state, signInWithGoogle, signOut, refreshUser],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
