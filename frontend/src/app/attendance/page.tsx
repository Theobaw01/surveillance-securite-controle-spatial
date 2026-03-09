"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Clock,
  Users,
  AlertTriangle,
  UserX,
  RefreshCw,
  CalendarDays,
  TrendingUp,
  Loader2,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import {
  getAttendanceToday,
  getAttendanceLate,
  getAttendanceAbsent,
  getAttendanceStats,
} from "@/lib/api";

type AttendanceRecord = Record<string, unknown>;

export default function AttendancePage() {
  const [tab, setTab] = useState<"today" | "late" | "absent" | "stats">(
    "today"
  );
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [stats, setStats] = useState<{
    total_inscrits: number;
    total_present: number;
    total_absent: number;
    total_retards: number;
    retard_moyen_min: number;
    retard_max_min: number;
    taux_presence: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (tab === "today") {
        const res = await getAttendanceToday();
        setRecords(res.records);
      } else if (tab === "late") {
        const res = await getAttendanceLate();
        setRecords(res.records);
      } else if (tab === "absent") {
        const res = await getAttendanceAbsent();
        setRecords(res.records);
      } else if (tab === "stats") {
        const res = await getAttendanceStats();
        setStats(res);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur chargement");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs = [
    { key: "today" as const, label: "Aujourd'hui", icon: CalendarDays },
    { key: "late" as const, label: "Retards", icon: AlertTriangle },
    { key: "absent" as const, label: "Absents", icon: UserX },
    { key: "stats" as const, label: "Statistiques", icon: TrendingUp },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Clock className="w-6 h-6" /> Suivi de présence
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Pointages, retards, absences et statistiques
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-card border border-surface-border text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-40"
        >
          <RefreshCw
            className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
          />
          Actualiser
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-surface-border pb-3">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === key
                ? "bg-brand-600 text-white"
                : "text-gray-400 hover:bg-surface-card hover:text-white"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Tab content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-brand-400" />
          <span className="ml-2 text-sm text-gray-400">Chargement...</span>
        </div>
      ) : tab === "stats" ? (
        stats && <StatsView stats={stats} />
      ) : tab === "absent" ? (
        <AbsentView records={records} />
      ) : (
        <AttendanceTable records={records} showRetard={tab === "late"} />
      )}
    </div>
  );
}

/* ── Stats View ── */
function StatsView({
  stats,
}: {
  stats: {
    total_inscrits: number;
    total_present: number;
    total_absent: number;
    total_retards: number;
    retard_moyen_min: number;
    retard_max_min: number;
    taux_presence: number;
  };
}) {
  const cards = [
    {
      label: "Inscrits",
      value: stats.total_inscrits,
      icon: Users,
      color: "text-blue-400",
    },
    {
      label: "Présents",
      value: stats.total_present,
      icon: CheckCircle2,
      color: "text-green-400",
    },
    {
      label: "Absents",
      value: stats.total_absent,
      icon: XCircle,
      color: "text-red-400",
    },
    {
      label: "Retards",
      value: stats.total_retards,
      icon: AlertTriangle,
      color: "text-orange-400",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div
            key={c.label}
            className="bg-surface-card border border-surface-border rounded-xl p-5"
          >
            <c.icon className={`w-5 h-5 ${c.color} mb-2`} />
            <p className="text-2xl font-bold text-white">{c.value}</p>
            <p className="text-xs text-gray-400 mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      {/* Large stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          <p className="text-xs text-gray-400 mb-1">Taux de présence</p>
          <p className="text-3xl font-bold text-brand-300">
            {stats.taux_presence}%
          </p>
          <div className="mt-3 h-2 bg-surface rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-500 rounded-full transition-all"
              style={{ width: `${stats.taux_presence}%` }}
            />
          </div>
        </div>
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          <p className="text-xs text-gray-400 mb-1">Retard moyen</p>
          <p className="text-3xl font-bold text-orange-300">
            {stats.retard_moyen_min}
            <span className="text-sm font-normal text-gray-400"> min</span>
          </p>
        </div>
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          <p className="text-xs text-gray-400 mb-1">Retard max</p>
          <p className="text-3xl font-bold text-red-300">
            {stats.retard_max_min}
            <span className="text-sm font-normal text-gray-400"> min</span>
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Attendance Table ── */
function AttendanceTable({
  records,
  showRetard,
}: {
  records: AttendanceRecord[];
  showRetard: boolean;
}) {
  if (records.length === 0) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-xl p-12 text-center">
        <Clock className="w-12 h-12 mx-auto text-gray-600 mb-2" />
        <p className="text-sm text-gray-500">
          {showRetard
            ? "Aucun retard enregistré aujourd'hui"
            : "Aucun pointage enregistré aujourd'hui"}
        </p>
        <p className="text-xs text-gray-600 mt-1">
          Uploadez une vidéo dans l&apos;onglet Détection pour enregistrer les
          présences
        </p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto max-h-[500px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-card">
            <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-surface-border">
              <th className="px-4 py-3">Personne</th>
              <th className="px-4 py-3">Direction</th>
              <th className="px-4 py-3">Heure</th>
              <th className="px-4 py-3">Similarité</th>
              {showRetard && <th className="px-4 py-3">Retard</th>}
              <th className="px-4 py-3">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {records.map((r, i) => (
              <tr
                key={i}
                className="hover:bg-surface-hover/40 transition-colors"
              >
                <td className="px-4 py-2.5 text-gray-200">
                  {(r.prenom as string) || ""} {(r.nom as string) || ""}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      r.direction === "entry"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-orange-500/20 text-orange-400"
                    }`}
                  >
                    {r.direction === "entry" ? "Entrée" : "Sortie"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">
                  {(r.datetime_str as string) || "—"}
                </td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">
                  {r.similarity
                    ? `${((r.similarity as number) * 100).toFixed(0)}%`
                    : "—"}
                </td>
                {showRetard && (
                  <td className="px-4 py-2.5">
                    {r.is_late ? (
                      <span className="text-xs text-red-400 font-medium">
                        +{(r.retard_minutes as number)?.toFixed(0)} min
                      </span>
                    ) : (
                      <span className="text-xs text-green-400">À l&apos;heure</span>
                    )}
                  </td>
                )}
                <td className="px-4 py-2.5 text-gray-500 text-xs font-mono">
                  {(r.camera_id as string) || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Absent View ── */
function AbsentView({ records }: { records: AttendanceRecord[] }) {
  if (records.length === 0) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-xl p-12 text-center">
        <CheckCircle2 className="w-12 h-12 mx-auto text-green-600 mb-2" />
        <p className="text-sm text-gray-400">
          Tout le monde est présent aujourd&apos;hui !
        </p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-surface-border">
              <th className="px-4 py-3">Personne</th>
              <th className="px-4 py-3">Groupe</th>
              <th className="px-4 py-3">Rôle</th>
              <th className="px-4 py-3">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {records.map((r, i) => (
              <tr
                key={i}
                className="hover:bg-surface-hover/40 transition-colors"
              >
                <td className="px-4 py-2.5 text-gray-200">
                  {(r.prenom as string) || ""} {(r.nom as string) || ""}
                </td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">
                  {(r.groupe as string) || "—"}
                </td>
                <td className="px-4 py-2.5 text-gray-400 text-xs">
                  {(r.role as string) || "—"}
                </td>
                <td className="px-4 py-2.5">
                  <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
                    Absent
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
