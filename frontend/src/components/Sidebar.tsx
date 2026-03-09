"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Camera,
  Users,
  FileBarChart,
  Image as ImageIcon,
  Shield,
  Clock,
  Settings,
} from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cameras", label: "Caméras", icon: Camera },
  { href: "/persons", label: "Personnes", icon: Users },
  { href: "/detect", label: "Détection", icon: ImageIcon },
  { href: "/attendance", label: "Présence", icon: Clock },
  { href: "/reports", label: "Rapports", icon: FileBarChart },
  { href: "/settings", label: "Paramètres", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 flex flex-col"
      style={{
        background: "#000000",
        borderRight: "1px solid rgba(255,255,255,0.05)",
      }}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{
            background: "linear-gradient(135deg, #6366f1, #4f46e5)",
            boxShadow: "0 4px 12px -2px rgba(99,102,241,0.25)",
          }}>
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-wide text-white">
            SURVEILLANCE-IA
          </h1>
          <span className="text-[10px] text-gray-400 tracking-wider uppercase">
            Projet SAHELYS
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200",
                active
                  ? "text-brand-400"
                  : "text-gray-500 hover:text-gray-300 hover:bg-white/5"
              )}
              style={active ? {
                background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(99,102,241,0.04))",
                boxShadow: "inset 0 0 0 1px rgba(99,102,241,0.15)",
              } : undefined}
            >
              <Icon className={clsx("w-[18px] h-[18px]", active ? "text-brand-500" : "")} />
              {label}
              {active && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-brand-500" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 text-[11px] text-gray-500" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
        <p className="text-gray-400">BAWANA Théodore</p>
        <p className="mt-0.5">YOLOv8 + InsightFace</p>
      </div>
    </aside>
  );
}
