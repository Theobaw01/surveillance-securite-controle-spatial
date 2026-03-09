"use client";

import Sidebar from "@/components/Sidebar";
import { AuthProvider, useAuth } from "@/lib/auth";

function AuthStatus() {
  const { ready, error } = useAuth();
  if (!ready) {
    return (
      <div className="fixed top-2 right-2 z-50 rounded bg-yellow-600 px-3 py-1 text-xs text-white animate-pulse">
        Connexion API…
      </div>
    );
  }
  if (error) {
    return (
      <div className="fixed top-2 right-2 z-50 rounded bg-red-600 px-3 py-1 text-xs text-white">
        {error}
      </div>
    );
  }
  return null;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthStatus />
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </AuthProvider>
  );
}
