"use client";

import Sidebar from "@/components/Sidebar";
import { AuthProvider, useAuth } from "@/lib/auth";

function AuthGate({ children }: { children: React.ReactNode }) {
  const { ready, loggedIn, error } = useAuth();

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-900 text-white">
        <p className="animate-pulse text-lg">Connexion en cours…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-900 text-red-400">
        <p>{error} — Vérifiez que l&apos;API est accessible.</p>
      </div>
    );
  }

  return (
    <>
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>{children}</AuthGate>
    </AuthProvider>
  );
}
