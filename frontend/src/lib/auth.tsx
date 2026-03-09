"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { login, isAuthenticated } from "@/lib/api";

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
 * AuthProvider — tries auto-login with default credentials
 * so protected API routes (stream/start, stream/stop) work.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function autoLogin() {
      // Already have a token?
      if (isAuthenticated()) {
        setLoggedIn(true);
        setReady(true);
        return;
      }

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
