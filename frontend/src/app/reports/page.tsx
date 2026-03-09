"use client";

import { useEffect, useState, useCallback } from "react";
import {
  FileBarChart,
  Download,
  RefreshCw,
  ChevronLeft,
  User,
  Clock,
  CalendarDays,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  LogIn,
  LogOut,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import {
  getPersons,
  getPersonAttendanceHistory,
  getAttendanceStats,
} from "@/lib/api";

/* ─── Types ─────────────────────────────────────────── */
interface Person {
  person_id: string;
  nom: string;
  prenom: string;
  groupe: string;
  role: string;
  organisation: string;
  created_at: string;
}

interface Segment {
  entry_time: string | null;
  exit_time: string | null;
  entry_ts: number | null;
  exit_ts: number | null;
  duration_sec: number;
}

interface DayEvent {
  direction: string;
  time: string;
  timestamp: number;
}

interface DailyRecord {
  date: string;
  present: boolean;
  first_entry_time: string | null;
  last_exit_time: string | null;
  duration_sec: number;
  duration_hours: number;
  entries_count: number;
  exits_count: number;
  is_late: boolean;
  retard_minutes: number;
  segments: Segment[];
  events: DayEvent[];
}

interface PersonHistory {
  person_id: string;
  nom: string;
  prenom: string;
  groupe: string;
  role: string;
  date_from: string;
  date_to: string;
  summary: {
    total_days: number;
    days_present: number;
    days_absent: number;
    taux_presence: number;
    total_duration_sec: number;
    avg_duration_sec: number;
    avg_duration_hours: number;
    total_late: number;
  };
  daily: DailyRecord[];
}

interface GlobalStats {
  total_inscrits: number;
  total_present: number;
  total_absent: number;
  total_retards: number;
  taux_presence: number;
}

/* ─── Helpers ───────────────────────────────────────── */
function fmtDuration(sec: number) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}min`;
  return `${m}min`;
}

function shortDate(d: string) {
  const parts = d.split("-");
  return `${parts[2]}/${parts[1]}`;
}

function dayLabel(d: string) {
  const days = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];
  const dt = new Date(d);
  return days[dt.getDay()];
}

/** Extract HH:MM from a datetime string like "2026-03-09 14:32:05" */
function extractTime(dt: string | null): string {
  if (!dt) return "";
  const parts = dt.split(" ");
  if (parts.length >= 2) return parts[1].slice(0, 5);
  return dt.slice(0, 5);
}

/** Convert "HH:MM" or "HH:MM:SS" to minutes since midnight */
function timeToMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

const PIE_COLORS = ["#22c55e", "#ef4444", "#f59e0b"];

/* ─── Period selector ───────────────────────────────── */
type Period = "7d" | "14d" | "30d";

function getPeriodDates(period: Period): { from: string; to: string } {
  const to = new Date();
  const toStr = to.toISOString().slice(0, 10);
  const from = new Date();
  switch (period) {
    case "7d":
      from.setDate(from.getDate() - 6);
      break;
    case "14d":
      from.setDate(from.getDate() - 13);
      break;
    case "30d":
      from.setDate(from.getDate() - 29);
      break;
  }
  return { from: from.toISOString().slice(0, 10), to: toStr };
}

/* ─── Timeline Bar Component ────────────────────────── */
function TimelineBar({ segments, events }: { segments: Segment[]; events: DayEvent[] }) {
  const DAY_START = 0;
  const DAY_END = 24 * 60;
  const TOTAL = DAY_END - DAY_START;

  const blocks: { startMin: number; endMin: number; durationSec: number }[] = [];
  for (const seg of segments) {
    const entryStr = extractTime(seg.entry_time);
    const exitStr = extractTime(seg.exit_time);
    if (!entryStr && !exitStr) continue;
    const s = entryStr ? timeToMinutes(entryStr) : DAY_START;
    const e = exitStr ? timeToMinutes(exitStr) : DAY_END;
    if (e > s) {
      blocks.push({ startMin: s, endMin: e, durationSec: seg.duration_sec });
    }
  }

  const hours = [0, 6, 12, 18, 24];

  return (
    <div className="w-full group/timeline">
      {/* Timeline track */}
      <div className="relative h-7 rounded-lg overflow-hidden"
        style={{ background: "linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.04) 50%, rgba(255,255,255,0.02) 100%)" }}>
        {/* Subtle hour grid lines */}
        {[6, 12, 18].map((h) => (
          <div
            key={h}
            className="absolute top-0 h-full w-px opacity-20"
            style={{ left: `${(h * 60 / TOTAL) * 100}%`, background: "linear-gradient(180deg, transparent, rgba(100,116,139,0.2), transparent)" }}
          />
        ))}

        {/* Presence blocks with gradient */}
        {blocks.map((b, i) => {
          const left = ((b.startMin - DAY_START) / TOTAL) * 100;
          const width = ((b.endMin - b.startMin) / TOTAL) * 100;
          return (
            <div
              key={i}
              className="absolute top-0.5 bottom-0.5 rounded-md transition-all duration-200"
              style={{
                left: `${left}%`,
                width: `${Math.max(width, 0.5)}%`,
                background: "linear-gradient(180deg, rgba(34,197,94,0.55) 0%, rgba(22,163,74,0.35) 100%)",
                boxShadow: "0 0 8px -2px rgba(34,197,94,0.2), inset 0 1px 0 rgba(255,255,255,0.3)",
                borderLeft: "1px solid rgba(34,197,94,0.3)",
                borderRight: "1px solid rgba(34,197,94,0.3)",
              }}
              title={`${Math.floor(b.startMin / 60)}:${String(b.startMin % 60).padStart(2, "0")} → ${Math.floor(b.endMin / 60)}:${String(b.endMin % 60).padStart(2, "0")} (${fmtDuration(b.durationSec)})`}
            />
          );
        })}

        {/* Event markers */}
        {events.map((ev, i) => {
          const t = extractTime(ev.time);
          if (!t) return null;
          const min = timeToMinutes(t);
          const pos = ((min - DAY_START) / TOTAL) * 100;
          const isEntry = ev.direction === "entry";
          return (
            <div
              key={i}
              className="absolute top-0 h-full w-[2px] rounded-full"
              style={{
                left: `${pos}%`,
                background: isEntry
                  ? "linear-gradient(180deg, rgba(52,211,153,0.9), rgba(52,211,153,0.3))"
                  : "linear-gradient(180deg, rgba(248,113,113,0.9), rgba(248,113,113,0.3))",
              }}
              title={`${isEntry ? "Entrée" : "Sortie"} ${t}`}
            />
          );
        })}
      </div>

      {/* Hour labels */}
      <div className="relative h-3.5 mt-0.5">
        {hours.map((h) => {
          const pos = ((h * 60 - DAY_START) / TOTAL) * 100;
          return (
            <span
              key={h}
              className="absolute text-[8px] font-medium tracking-wide text-gray-400/60 -translate-x-1/2"
              style={{ left: `${pos}%` }}
            >
              {h === 24 ? "" : `${h}h`}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   Main Reports Page
   ═══════════════════════════════════════════════════════ */
export default function ReportsPage() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [history, setHistory] = useState<PersonHistory | null>(null);
  const [globalStats, setGlobalStats] = useState<GlobalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [period, setPeriod] = useState<Period>("30d");
  const [searchTerm, setSearchTerm] = useState("");

  /* Load persons list + global stats */
  const loadPersons = useCallback(async () => {
    setLoading(true);
    try {
      const [p, stats] = await Promise.all([
        getPersons(),
        getAttendanceStats(),
      ]);
      setPersons(p.persons || []);
      setGlobalStats(stats as GlobalStats);
    } catch {
      // offline
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPersons();
  }, [loadPersons]);

  /* Load selected person's history */
  const loadHistory = useCallback(
    async (person: Person, p: Period) => {
      setHistoryLoading(true);
      try {
        const { from, to } = getPeriodDates(p);
        const h = await getPersonAttendanceHistory(person.person_id, from, to);
        setHistory(h);
      } catch {
        setHistory(null);
      } finally {
        setHistoryLoading(false);
      }
    },
    []
  );

  function selectPerson(person: Person) {
    setSelectedPerson(person);
    loadHistory(person, period);
  }

  function changePeriod(p: Period) {
    setPeriod(p);
    if (selectedPerson) loadHistory(selectedPerson, p);
  }

  function goBack() {
    setSelectedPerson(null);
    setHistory(null);
  }

  /* Export CSV */
  function exportPersonCSV() {
    if (!history) return;
    const header =
      "Date,Jour,Présent,Première entrée,Dernière sortie,Segments,Durée totale,Retard,Retard (min)\n";
    const rows = history.daily
      .map((d) => {
        const segs = d.segments
          .map(
            (s) =>
              `${extractTime(s.entry_time) || "?"}-${extractTime(s.exit_time) || "?"}`
          )
          .join(" | ");
        return `${d.date},${dayLabel(d.date)},${d.present ? "Oui" : "Non"},${extractTime(d.first_entry_time)},${extractTime(d.last_exit_time)},"${segs}",${d.duration_hours}h,${d.is_late ? "Oui" : "Non"},${d.retard_minutes}`;
      })
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rapport_${history.prenom}_${history.nom}_${history.date_from}_${history.date_to}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const filteredPersons = persons.filter((p) => {
    const term = searchTerm.toLowerCase();
    return (
      p.nom.toLowerCase().includes(term) ||
      p.prenom.toLowerCase().includes(term) ||
      p.groupe.toLowerCase().includes(term) ||
      p.role.toLowerCase().includes(term)
    );
  });

  /* ═══════════════════════════════════════════
     Person Detail View — Timeline + Graphs
     ═══════════════════════════════════════════ */
  if (selectedPerson && history) {
    const s = history.summary;

    const barData = history.daily.map((d) => ({
      date: shortDate(d.date),
      day: dayLabel(d.date),
      heures: d.duration_hours,
      present: d.present ? 1 : 0,
      retard: d.retard_minutes,
    }));

    const pieData = [
      { name: "Présent", value: s.days_present },
      { name: "Absent", value: s.days_absent },
      ...(s.total_late > 0
        ? [{ name: "En retard", value: s.total_late }]
        : []),
    ];

    return (
      <div className="space-y-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <button
              onClick={goBack}
              title="Retour"
              className="p-2.5 rounded-xl glass-card hover:bg-surface-hover/60 transition-all duration-200 group/back"
            >
              <ChevronLeft className="w-4 h-4 text-gray-400 group-hover/back:text-brand-500 transition-colors" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                {history.prenom} {history.nom}
              </h1>
              <p className="text-sm text-gray-500 mt-0.5">
                {history.role && (
                  <span className="capitalize text-gray-400">{history.role}</span>
                )}
                {history.groupe && <span className="text-gray-400"> · </span>}
                {history.groupe && <span className="text-gray-400">{history.groupe}</span>}
                <span className="text-gray-400"> · </span>
                <span className="text-gray-500">{history.date_from} → {history.date_to}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(["7d", "14d", "30d"] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => changePeriod(p)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                  period === p
                    ? "bg-brand-600/90 text-white shadow-glow"
                    : "glass-card text-gray-400 hover:text-gray-300"
                }`}
              >
                {p === "7d"
                  ? "7 jours"
                  : p === "14d"
                    ? "14 jours"
                    : "30 jours"}
              </button>
            ))}
            <button
              onClick={exportPersonCSV}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 bg-brand-600/90 text-white hover:bg-brand-500 shadow-glow"
            >
              <Download className="w-3.5 h-3.5" />
              CSV
            </button>
          </div>
        </div>

        {historyLoading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" />
            Chargement...
          </div>
        ) : (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <SummaryCard
                icon={<CalendarDays className="w-4 h-4" />}
                label="Taux de présence"
                value={`${s.taux_presence}%`}
                accent={
                  s.taux_presence >= 80
                    ? "emerald"
                    : s.taux_presence >= 50
                      ? "yellow"
                      : "red"
                }
              />
              <SummaryCard
                icon={<CheckCircle2 className="w-4 h-4" />}
                label="Jours présent"
                value={`${s.days_present} / ${s.total_days}`}
                accent="emerald"
              />
              <SummaryCard
                icon={<XCircle className="w-4 h-4" />}
                label="Jours absent"
                value={String(s.days_absent)}
                accent="red"
              />
              <SummaryCard
                icon={<Clock className="w-4 h-4" />}
                label="Durée moy."
                value={`${s.avg_duration_hours}h`}
                accent="blue"
              />
              <SummaryCard
                icon={<AlertTriangle className="w-4 h-4" />}
                label="Retards"
                value={String(s.total_late)}
                accent="amber"
              />
            </div>

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {/* Bar chart */}
              <div className="lg:col-span-2 glass-card rounded-2xl p-5">
                <h3 className="text-sm font-semibold text-gray-400 mb-5 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-brand-500" />
                  Heures de présence par jour
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={barData}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.04)"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: "#666", fontSize: 10 }}
                        axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                        tickLine={false}
                        interval={barData.length > 15 ? 1 : 0}
                        angle={barData.length > 15 ? -45 : 0}
                        textAnchor={
                          barData.length > 15 ? "end" : "middle"
                        }
                        height={barData.length > 15 ? 50 : 30}
                      />
                      <YAxis
                        tick={{ fill: "#666", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        label={{
                          value: "Heures",
                          angle: -90,
                          position: "insideLeft",
                          fill: "#94a3b8",
                          fontSize: 11,
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "rgba(12,12,12,0.95)",
                          border: "1px solid rgba(255,255,255,0.06)",
                          borderRadius: 12,
                          color: "#e2e8f0",
                          fontSize: 12,
                          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                        }}
                        formatter={(value: number) => [
                          `${value}h`,
                          "Durée",
                        ]}
                        labelFormatter={(label) => {
                          const item = barData.find(
                            (d) => d.date === label
                          );
                          return item
                            ? `${item.day} ${label}`
                            : String(label);
                        }}
                        cursor={{ fill: "rgba(255,255,255,0.02)" }}
                      />
                      <Bar dataKey="heures" radius={[6, 6, 0, 0]}>
                        {barData.map((entry, idx) => (
                          <Cell
                            key={idx}
                            fill={
                              entry.heures === 0
                                ? "rgba(255,255,255,0.04)"
                                : entry.retard > 0
                                  ? "#f59e0b"
                                  : "#22c55e"
                            }
                            opacity={entry.heures === 0 ? 0.3 : 0.8}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex items-center gap-5 mt-4 text-[11px] text-gray-500">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    Présent
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-yellow-500" />
                    En retard
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-gray-600" />
                    Absent
                  </span>
                </div>
              </div>

              {/* Pie chart */}
              <div className="glass-card rounded-2xl p-5">
                <h3 className="text-sm font-semibold text-gray-400 mb-5 flex items-center gap-2">
                  <CalendarDays className="w-4 h-4 text-brand-500" />
                  Répartition
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        dataKey="value"
                        label={({ name, value }) =>
                          `${name}: ${value}`
                        }
                        labelLine={false}
                        stroke="rgba(0,0,0,0.1)"
                        strokeWidth={2}
                      >
                        {pieData.map((_entry, idx) => (
                          <Cell
                            key={idx}
                            fill={
                              PIE_COLORS[idx % PIE_COLORS.length]
                            }
                          />
                        ))}
                      </Pie>
                      <Legend
                        wrapperStyle={{
                          fontSize: 11,
                          color: "#999",
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "rgba(12,12,12,0.95)",
                          border: "1px solid rgba(255,255,255,0.06)",
                          borderRadius: 12,
                          color: "#e2e8f0",
                          fontSize: 12,
                          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* ══════ Day-by-day detail with timeline ══════ */}
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-surface-border/50 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-300 tracking-tight">
                  Détail jour par jour
                </h3>
                <div className="flex items-center gap-4 text-[10px] text-gray-500">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-1.5 rounded-full" style={{ background: "linear-gradient(90deg, rgba(34,197,94,0.6), rgba(22,163,74,0.4))" }} /> Présent
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3 h-1.5 rounded-full bg-gray-700/50" /> Absent
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-[3px] h-3 rounded-full bg-emerald-400/70" /> Entrée
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-[3px] h-3 rounded-full bg-red-400/70" /> Sortie
                  </span>
                </div>
              </div>
              <div className="overflow-y-auto max-h-[600px]">
                {[...history.daily].reverse().map((d, idx) => (
                  <div
                    key={d.date}
                    className="px-5 py-3.5 border-b border-surface-border/30 last:border-0 transition-colors duration-150 hover:bg-slate-50/50"
                    style={{ animationDelay: `${idx * 30}ms` }}
                  >
                    {/* Row 1: Date + status + timeline + duration */}
                    <div className="flex items-center gap-4">
                      <div className="w-16 shrink-0">
                        <p className="text-xs text-gray-400 font-mono tracking-tight">{shortDate(d.date)}</p>
                        <p className="text-[10px] text-gray-400 font-medium">{dayLabel(d.date)}</p>
                      </div>
                      <div className="w-[70px] shrink-0">
                        {d.present ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            Présent
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-500/10 text-gray-500 border border-gray-500/15">
                            <span className="w-1.5 h-1.5 rounded-full bg-gray-500" />
                            Absent
                          </span>
                        )}
                      </div>
                      {/* Timeline bar */}
                      <div className="flex-1 min-w-0">
                        {d.present ? (
                          <TimelineBar segments={d.segments} events={d.events} />
                        ) : (
                          <div className="h-7 rounded-lg flex items-center justify-center" style={{ background: "rgba(255,255,255,0.03)" }}>
                            <span className="text-[10px] text-gray-300">—</span>
                          </div>
                        )}
                      </div>
                      {/* Duration */}
                      <div className="w-24 shrink-0 text-right">
                        <p className="text-xs text-gray-400 font-mono tracking-tight">
                          {d.duration_sec > 0 ? fmtDuration(d.duration_sec) : "—"}
                        </p>
                        {d.is_late && (
                          <p className="text-[10px] text-amber-400/80 font-medium">
                            +{Math.round(d.retard_minutes)} min
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Row 2: Segments detail */}
                    {d.present && d.segments.length > 0 && (
                      <div className="ml-16 pl-4 mt-2 flex flex-wrap gap-1.5">
                        {d.segments.map((seg, si) => (
                          <div
                            key={si}
                            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] transition-colors duration-150"
                            style={{
                              background: "rgba(255,255,255,0.04)",
                              border: "1px solid rgba(255,255,255,0.06)",
                            }}
                          >
                            <span className="w-1 h-1 rounded-full bg-emerald-400/70" />
                            <span className="text-gray-400 font-mono">
                              {extractTime(seg.entry_time) || "?"}
                            </span>
                            <span className="text-gray-400">→</span>
                            <span className="w-1 h-1 rounded-full bg-red-400/70" />
                            <span className="text-gray-400 font-mono">
                              {extractTime(seg.exit_time) || "?"}
                            </span>
                            {seg.duration_sec > 0 && (
                              <span className="text-gray-400 ml-0.5 font-medium">
                                {fmtDuration(seg.duration_sec)}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    );
  }

  /* ═══════════════════════════════════════════
     Persons List View (clickable cards)
     ═══════════════════════════════════════════ */
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-brand-600/15">
              <FileBarChart className="w-5 h-5 text-brand-500" />
            </div>
            Rapports
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Cliquez sur une personne pour voir son rapport détaillé
          </p>
        </div>
        <button
          onClick={loadPersons}
          disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 glass-card rounded-xl text-xs text-gray-400 hover:text-gray-300 transition-all duration-200"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
          />
          Actualiser
        </button>
      </div>

      {/* Global stats */}
      {globalStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard
            icon={<User className="w-4 h-4" />}
            label="Inscrits"
            value={String(globalStats.total_inscrits)}
            accent="indigo"
          />
          <SummaryCard
            icon={<CheckCircle2 className="w-4 h-4" />}
            label="Présents aujourd'hui"
            value={String(globalStats.total_present)}
            accent="emerald"
          />
          <SummaryCard
            icon={<XCircle className="w-4 h-4" />}
            label="Absents"
            value={String(globalStats.total_absent)}
            accent="red"
          />
          <SummaryCard
            icon={<AlertTriangle className="w-4 h-4" />}
            label="Retards"
            value={String(globalStats.total_retards)}
            accent="amber"
          />
          <SummaryCard
            icon={<TrendingUp className="w-4 h-4" />}
            label="Taux présence"
            value={`${globalStats.taux_presence}%`}
            accent={
              globalStats.taux_presence >= 80
                ? "emerald"
                : "yellow"
            }
          />
        </div>
      )}

      {/* Search */}
      <div className="relative group/search">
        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
          <svg className="w-4 h-4 text-gray-500 transition-colors group-focus-within/search:text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <input
          type="text"
          placeholder="Rechercher une personne..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full glass-card rounded-xl pl-10 pr-4 py-2.5 text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition-all duration-200"
        />
      </div>

      {/* Persons grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <RefreshCw className="w-5 h-5 animate-spin mr-2" />
          <span className="text-sm">Chargement...</span>
        </div>
      ) : filteredPersons.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-surface-card flex items-center justify-center">
            <User className="w-7 h-7 opacity-30" />
          </div>
          <p className="text-sm font-medium text-gray-400">Aucune personne enregistrée</p>
          <p className="text-xs mt-1 text-gray-400">
            Enregistrez des personnes dans l&apos;onglet
            &quot;Personnes&quot;
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredPersons.map((person, idx) => (
            <button
              key={person.person_id}
              onClick={() => selectPerson(person)}
              className="glass-card rounded-2xl p-4 text-left hover:shadow-card-hover transition-all duration-300 group"
              style={{ animationDelay: `${idx * 40}ms` }}
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors duration-200"
                  style={{ background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(99,102,241,0.03))" }}>
                  <User className="w-5 h-5 text-brand-500/80" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-200 group-hover:text-brand-600 transition-colors duration-200 truncate">
                    {person.prenom} {person.nom}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {person.role && (
                      <span className="capitalize text-gray-400">
                        {person.role}
                      </span>
                    )}
                    {person.groupe && (
                      <span className="text-gray-400"> · {person.groupe}</span>
                    )}
                  </p>
                  {person.organisation && (
                    <p className="text-[11px] text-gray-400 mt-0.5 truncate">
                      {person.organisation}
                    </p>
                  )}
                </div>
                <div className="p-1 rounded-lg group-hover:bg-brand-600/10 transition-colors duration-200">
                  <ChevronLeft className="w-4 h-4 text-gray-300 rotate-180 group-hover:text-brand-500 transition-colors duration-200 shrink-0" />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Reusable Summary Card ────────────────────────── */
const ACCENT_MAP: Record<string, { bg: string; border: string; text: string; iconColor: string }> = {
  emerald: { bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.2)", text: "text-emerald-400", iconColor: "text-emerald-500" },
  red:     { bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.2)",   text: "text-red-400",     iconColor: "text-red-400" },
  amber:   { bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.2)",  text: "text-yellow-400",   iconColor: "text-amber-500" },
  yellow:  { bg: "rgba(234,179,8,0.08)",   border: "rgba(234,179,8,0.2)",   text: "text-yellow-400",  iconColor: "text-yellow-500" },
  blue:    { bg: "rgba(59,130,246,0.08)",   border: "rgba(59,130,246,0.2)",  text: "text-blue-400",    iconColor: "text-blue-500" },
  indigo:  { bg: "rgba(99,102,241,0.08)",   border: "rgba(99,102,241,0.2)",  text: "text-brand-400",   iconColor: "text-brand-500" },
};

function SummaryCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: string;
}) {
  const a = ACCENT_MAP[accent] || ACCENT_MAP.indigo;
  return (
    <div
      className="rounded-2xl p-4 transition-all duration-200 hover:scale-[1.02]"
      style={{
        background: `linear-gradient(135deg, ${a.bg}, rgba(10,10,10,0.6))`,
        border: `1px solid ${a.border}`,
        boxShadow: "0 1px 6px -2px rgba(0,0,0,0.3)",
      }}
    >
      <div className="flex items-center gap-2 mb-2.5">
        <span className={a.iconColor}>{icon}</span>
        <span className="text-[11px] text-gray-500 font-medium">{label}</span>
      </div>
      <p className={`text-xl font-bold tracking-tight ${a.text}`}>{value}</p>
    </div>
  );
}
