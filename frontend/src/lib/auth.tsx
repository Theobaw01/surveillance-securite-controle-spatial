"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { logout } from "@/lib/api";

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
        // Timeout after 5s to prevent UI hanging forever
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);

        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"}/auth/token`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: "admin", password: "admin_surv_2024" }),
            signal: controller.signal,
          }
        );
        clearTimeout(timeout);

        if (res.ok) {
          const data = await res.json();
          localStorage.setItem("surv_token", data.access_token);
          setLoggedIn(true);
        } else {
          console.warn("Auto-login HTTP error:", res.status);
          setError(`Login échoué (${res.status})`);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn("Auto-login failed:", msg);
        setError("API inaccessible");
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
