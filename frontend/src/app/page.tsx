"use client";

import { useEffect, useState } from "react";
import StatsCards from "@/components/StatsCards";
import LiveFeed from "@/components/LiveFeed";
import AlertPanel from "@/components/AlertPanel";
import OccupancyChart from "@/components/OccupancyChart";
import { useWebSocket } from "@/lib/useWebSocket";
import {
  getHealth,
  getStats,
  getAlerts,
  getStreamStatus,
  getInspectionStatus,
  getPresenceDuration,
} from "@/lib/api";
import {
  Wifi,
  WifiOff,
  UserCheck,
  Clock,
  LogIn,
  LogOut,
  ScanFace,
} from "lucide-react";

interface PresenceRecord {
  person_id: string;
  nom: string;
  prenom: string;
  entry_time: string;
  exit_time: string | null;
  still_present: boolean;
  duration_sec: number;
  duration_formatted: string;
}

interface InspectPerson {
  person_id: string;
  full_name: string;
  entry_time: string;
  duration_formatted: string;
  similarity: number;
}

export default function DashboardPage() {
  const { connected, stats: wsStats } = useWebSocket();
  const [apiOnline, setApiOnline] = useState(false);
  const [streamRunning, setStreamRunning] = useState(false);
  const [inspectionActive, setInspectionActive] = useState(false);
  const [presentPersons, setPresentPersons] = useState<InspectPerson[]>([]);
  const [presenceRecords, setPresenceRecords] = useState<PresenceRecord[]>([]);
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

        // Inspection status
        const insp = await getInspectionStatus();
        setInspectionActive(insp.active);
        setPresentPersons(insp.present_persons as InspectPerson[]);

        // Presence duration today
        const pres = await getPresenceDuration();
        setPresenceRecords(pres.records as PresenceRecord[]);
      } catch {
        setApiOnline(false);
      }
    };

    poll();
    const interval = setInterval(poll, 3000);
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

  function fmtTime(dt: string | null) {
    if (!dt) return "-";
    return dt.split(" ")[1] || dt;
  }

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
          {inspectionActive && (
            <span className="flex items-center gap-1.5 text-xs text-green-400 bg-green-500/10 px-2.5 py-1 rounded-full">
              <ScanFace className="w-3 h-3" />
              Inspection active
            </span>
          )}
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

      {/* Live feed + Présences en direct */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <LiveFeed cameraId="cam_01" isRunning={streamRunning} />
        </div>
        <div className="space-y-4">
          {/* Personnes présentes en temps réel */}
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-green-400" />
                En direct
              </h3>
              <span className="text-xs font-mono text-brand-400 bg-brand-500/10 px-2 py-0.5 rounded-full">
                {presentPersons.length} présent(s)
              </span>
            </div>
            <div className="max-h-[220px] overflow-y-auto">
              {!inspectionActive ? (
                <div className="p-4 text-center text-gray-500 text-sm">
                  <ScanFace className="w-6 h-6 mx-auto mb-1.5 opacity-30" />
                  Inspection inactive
                </div>
              ) : presentPersons.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">
                  En attente de détection...
                </div>
              ) : (
                presentPersons.map((p) => (
                  <div
                    key={p.person_id}
                    className="px-4 py-2.5 border-b border-surface-border last:border-0 flex items-center justify-between"
                  >
                    <div>
                      <p className="text-sm font-medium text-white">{p.full_name}</p>
                      <p className="text-[11px] text-gray-500">
                        Entrée {fmtTime(p.entry_time)}
                      </p>
                    </div>
                    <p className="text-xs font-mono text-green-400">{p.duration_formatted}</p>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Séjours du jour */}
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                <Clock className="w-4 h-4 text-yellow-400" />
                Séjours du jour
              </h3>
              <span className="text-xs text-gray-400">
                {presenceRecords.length} personne(s)
              </span>
            </div>
            <div className="max-h-[220px] overflow-y-auto">
              {presenceRecords.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">
                  Aucune donnée aujourd&apos;hui
                </div>
              ) : (
                presenceRecords.map((r) => (
                  <div
                    key={r.person_id}
                    className="px-4 py-2.5 border-b border-surface-border last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-gray-200">{r.prenom} {r.nom}</p>
                      <p className="text-xs font-mono text-yellow-400">
                        {r.duration_formatted}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-500">
                      <span className="flex items-center gap-1">
                        <LogIn className="w-3 h-3 text-green-500" />
                        {fmtTime(r.entry_time)}
                      </span>
                      <span className="flex items-center gap-1">
                        <LogOut className="w-3 h-3 text-red-400" />
                        {r.still_present ? (
                          <span className="text-green-400">Présent</span>
                        ) : (
                          fmtTime(r.exit_time)
                        )}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Chart */}
      <OccupancyChart data={stats.hourly} />
    </div>
  );
}
