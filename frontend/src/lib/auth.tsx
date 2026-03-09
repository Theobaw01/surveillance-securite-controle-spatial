"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { login, logout, isAuthenticated } from "@/lib/api";

interface AuthContextType {
  ready: boolean;
  loggedIn: boolean;
  error: string | null;
}

const AuthContext = createContext<AuthContextType>({
  ready: false,
  loggedIn: false,
  error: null,
});

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * AuthProvider — always performs a fresh login on mount to guarantee
 * a valid token, avoiding stale/expired token issues.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function autoLogin() {
      // Always clear any old token and do a fresh login
      logout();

      try {
        await login("admin", "admin_surv_2024");
        setLoggedIn(true);
      } catch (err) {
        console.warn("Auto-login failed:", err);
        setError("Auto-login échoué");
      } finally {
        setReady(true);
      }
    }

    autoLogin();
  }, []);

  return (
    <AuthContext.Provider value={{ ready, loggedIn, error }}>
      {children}
    </AuthContext.Provider>
  );
}
