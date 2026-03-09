"use client";

import { Users, DoorOpen, DoorClosed, Activity, Eye, Clock } from "lucide-react";
import clsx from "clsx";

interface Props {
  occupancy: number;
  entries: number;
  exits: number;
  fps: number;
  activeSessions: number;
  uptime: number;
}

function formatUptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

const cards = [
  {
    key: "occupancy",
    label: "Occupation",
    icon: Users,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    key: "entries",
    label: "Entrées",
    icon: DoorOpen,
    color: "text-green-400",
    bg: "bg-green-500/10",
  },
  {
    key: "exits",
    label: "Sorties",
    icon: DoorClosed,
    color: "text-orange-400",
    bg: "bg-orange-500/10",
  },
  {
    key: "fps",
    label: "FPS",
    icon: Activity,
    color: "text-purple-400",
    bg: "bg-purple-500/10",
  },
  {
    key: "activeSessions",
    label: "Personnes actives",
    icon: Eye,
    color: "text-cyan-400",
    bg: "bg-cyan-500/10",
  },
  {
    key: "uptime",
    label: "Uptime",
    icon: Clock,
    color: "text-yellow-400",
    bg: "bg-yellow-500/10",
  },
] as const;

export default function StatsCards(props: Props) {
  const values: Record<string, string | number> = {
    occupancy: props.occupancy,
    entries: props.entries,
    exits: props.exits,
    fps: props.fps.toFixed(1),
    activeSessions: props.activeSessions,
    uptime: formatUptime(props.uptime),
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
      {cards.map(({ key, label, icon: Icon, color, bg }) => (
        <div
          key={key}
          className="bg-surface-card border border-surface-border rounded-xl p-4 animate-fade-in"
        >
          <div className="flex items-center gap-2 mb-2">
            <div className={clsx("w-8 h-8 rounded-lg flex items-center justify-center", bg)}>
              <Icon className={clsx("w-4 h-4", color)} />
            </div>
          </div>
          <p className="text-2xl font-bold text-white">{values[key]}</p>
          <p className="text-xs text-gray-500 mt-1">{label}</p>
        </div>
      ))}
    </div>
  );
}
