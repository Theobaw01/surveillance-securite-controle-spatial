"use client";

import { useEffect, useState } from "react";
import StatsCards from "@/components/StatsCards";
import LiveFeed from "@/components/LiveFeed";
import AlertPanel from "@/components/AlertPanel";
import OccupancyChart from "@/components/OccupancyChart";
import { useWebSocket } from "@/lib/useWebSocket";
import { getHealth, getStats, getAlerts, getStreamStatus } from "@/lib/api";
import { Wifi, WifiOff } from "lucide-react";

export default function DashboardPage() {
  const { connected, stats: wsStats } = useWebSocket();
  const [apiOnline, setApiOnline] = useState(false);
  const [streamRunning, setStreamRunning] = useState(false);
  const [alerts, setAlerts] = useState<Array<{
    id: number;
    alert_type: string;
    message: string;
    datetime: string;
    acknowledged: boolean;
  }>>([]);
  const [stats, setStats] = useState({
    occupancy: 0,
    entries: 0,
    exits: 0,
    fps: 0,
    activeSessions: 0,
    uptime: 0,
    hourly: {} as Record<string, number>,
  });

  // Poll API
  useEffect(() => {
    const poll = async () => {
      try {
        const health = await getHealth();
        setApiOnline(health.status === "healthy");

        const status = await getStreamStatus();
        setStreamRunning(status.is_running);

        const s = await getStats();
        setStats({
          occupancy: s.current_occupancy,
          entries: s.total_entries,
          exits: s.total_exits,
          fps: s.fps,
          activeSessions: s.active_persons,
          uptime: s.uptime_seconds,
          hourly: {},
        });

        const a = await getAlerts();
        setAlerts(a.alerts as typeof alerts);
      } catch {
        setApiOnline(false);
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []);

  // Override avec WebSocket quand connecté
  useEffect(() => {
    if (wsStats) {
      setStats((prev) => ({
        ...prev,
        occupancy: wsStats.current_occupancy,
        entries: wsStats.total_entries,
        exits: wsStats.total_exits,
        fps: wsStats.fps,
        activeSessions: wsStats.active_persons,
        uptime: wsStats.uptime_seconds,
        hourly: wsStats.hourly_histogram ?? prev.hourly,
      }));
      setStreamRunning(wsStats.is_running);
    }
  }, [wsStats]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Suivi en temps réel — Surveillance-IA
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs">
            {apiOnline ? (
              <>
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse-green" />
                <span className="text-green-400">API en ligne</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-red-400" />
                <span className="text-red-400">API hors ligne</span>
              </>
            )}
          </span>
          <span className="flex items-center gap-1.5 text-xs">
            {connected ? (
              <>
                <Wifi className="w-3 h-3 text-green-400" />
                <span className="text-green-400">WS</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3 text-gray-500" />
                <span className="text-gray-500">WS</span>
              </>
            )}
          </span>
        </div>
      </div>

      {/* Stats cards */}
      <StatsCards
        occupancy={stats.occupancy}
        entries={stats.entries}
        exits={stats.exits}
        fps={stats.fps}
        activeSessions={stats.activeSessions}
        uptime={stats.uptime}
      />

      {/* Live feed + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <LiveFeed cameraId="cam_01" isRunning={streamRunning} />
        </div>
        <div>
          <AlertPanel alerts={alerts} />
        </div>
      </div>

      {/* Chart */}
      <OccupancyChart data={stats.hourly} />
    </div>
  );
}
