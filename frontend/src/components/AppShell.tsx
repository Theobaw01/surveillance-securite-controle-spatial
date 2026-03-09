"use client";

import Sidebar from "@/components/Sidebar";
import { AuthProvider } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </AuthProvider>
  );
}
