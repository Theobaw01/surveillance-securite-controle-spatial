"use client";

import { useEffect, useState } from "react";
import { FileBarChart, Download, RefreshCw } from "lucide-react";
import { getEvents, getAlerts, getStats } from "@/lib/api";

interface EventRow {
  track_id?: number;
  direction?: string;
  timestamp?: number;
  line_name?: string;
  datetime_str?: string;
}

export default function ReportsPage() {
  const [events, setEvents] = useState<EventRow[]>([]);
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [evts, s] = await Promise.all([getEvents(), getStats()]);
      setEvents((evts.events || []) as EventRow[]);
      setStats(s as Record<string, unknown>);
    } catch {
      // offline
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function exportCSV() {
    const header = "track_id,direction,timestamp,line_name\n";
    const rows = events
      .map(
        (e) =>
          `${e.track_id ?? ""},${e.direction ?? ""},${e.datetime_str ?? e.timestamp ?? ""},${e.line_name ?? ""}`
      )
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rapport_surveillance_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileBarChart className="w-6 h-6" /> Rapports
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Historique des événements de passage
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-2 bg-surface-card border border-surface-border rounded-lg text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Actualiser
          </button>
          <button
            onClick={exportCSV}
            disabled={events.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white rounded-lg text-xs font-medium hover:bg-brand-700 transition-colors disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" />
            Exporter CSV
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total événements", value: events.length },
          {
            label: "Entrées",
            value:
              events.filter((e) => e.direction === "IN").length,
          },
          {
            label: "Sorties",
            value:
              events.filter((e) => e.direction === "OUT").length,
          },
          {
            label: "Personnes uniques",
            value: (stats.total_unique_persons as number) ?? "—",
          },
        ].map((card) => (
          <div
            key={card.label}
            className="bg-surface-card border border-surface-border rounded-xl p-4"
          >
            <p className="text-2xl font-bold text-white">{card.value}</p>
            <p className="text-xs text-gray-400 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Events table */}
      <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border">
          <h3 className="text-sm font-semibold text-gray-300">
            Événements de passage
          </h3>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-gray-500">
            Chargement...
          </div>
        ) : events.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            Aucun événement enregistré.
            <br />
            Démarrez un flux pour commencer le tracking.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-card">
                <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-surface-border">
                  <th className="px-4 py-3">#</th>
                  <th className="px-4 py-3">Track ID</th>
                  <th className="px-4 py-3">Direction</th>
                  <th className="px-4 py-3">Ligne</th>
                  <th className="px-4 py-3">Heure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {events.map((evt, idx) => (
                  <tr
                    key={idx}
                    className="hover:bg-surface-hover/40 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-gray-500 text-xs">
                      {idx + 1}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-400">
                      {evt.track_id ?? "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          evt.direction === "IN"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-orange-500/20 text-orange-400"
                        }`}
                      >
                        {evt.direction || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs">
                      {evt.line_name || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs">
                      {evt.datetime_str || (evt.timestamp ? new Date(evt.timestamp * 1000).toLocaleTimeString("fr-FR") : "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
