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
} from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cameras", label: "Caméras", icon: Camera },
  { href: "/persons", label: "Personnes", icon: Users },
  { href: "/detect", label: "Détection", icon: ImageIcon },
  { href: "/reports", label: "Rapports", icon: FileBarChart },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 bg-surface-card border-r border-surface-border flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-surface-border">
        <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
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
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                active
                  ? "bg-brand-600/20 text-brand-200"
                  : "text-gray-400 hover:bg-surface-hover hover:text-gray-200"
              )}
            >
              <Icon className="w-[18px] h-[18px]" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-surface-border text-[11px] text-gray-500">
        <p>BAWANA Théodore</p>
        <p className="mt-0.5">YOLOv8 + InsightFace</p>
      </div>
    </aside>
  );
}
