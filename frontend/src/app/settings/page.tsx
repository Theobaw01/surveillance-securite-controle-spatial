"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Settings,
  Save,
  RefreshCw,
  Clock,
  Eye,
  Camera,
  Bell,
  AlertTriangle,
  CheckCircle2,
  FileDown,
  Timer,
  Plus,
  Trash2,
} from "lucide-react";
import { getSettings, updateSettings } from "@/lib/api";

interface TimePeriod {
  start: string;
  end: string;
}

interface AppSettings {
  recording_periods: TimePeriod[];
  absence_timeout_sec: number;
  face_recognition_threshold: number;
  face_recognition_interval: number;
  late_threshold_minutes: number;
  camera_source: string;
  auto_start_inspection: boolean;
  notification_enabled: boolean;
  export_format: string;
}

const DEFAULTS: AppSettings = {
  recording_periods: [],
  absence_timeout_sec: 20,
  face_recognition_threshold: 0.4,
  face_recognition_interval: 5,
  late_threshold_minutes: 15,
  camera_source: "0",
  auto_start_inspection: false,
  notification_enabled: false,
  export_format: "csv",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await getSettings();
      setSettings({
        ...DEFAULTS,
        ...s,
        recording_periods: Array.isArray(s.recording_periods)
          ? s.recording_periods
          : [],
      });
    } catch {
      // keep defaults
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateSettings(settings as unknown as Record<string, unknown>);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setError("Erreur lors de la sauvegarde");
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof AppSettings>(key: K, val: AppSettings[K]) {
    setSettings((prev) => ({ ...prev, [key]: val }));
    setSaved(false);
  }

  /* Period helpers */
  function addPeriod() {
    update("recording_periods", [
      ...settings.recording_periods,
      { start: "", end: "" },
    ]);
  }

  function removePeriod(idx: number) {
    update(
      "recording_periods",
      settings.recording_periods.filter((_, i) => i !== idx)
    );
  }

  function updatePeriod(idx: number, field: "start" | "end", val: string) {
    const updated = settings.recording_periods.map((p, i) =>
      i === idx ? { ...p, [field]: val } : p
    );
    update("recording_periods", updated);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        Chargement des paramètres...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-brand-600/15">
              <Settings className="w-5 h-5 text-brand-500" />
            </div>
            Paramètres
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Configuration générale de la surveillance
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-50 text-white"
          style={{
            background: saved
              ? "linear-gradient(135deg, #16a34a, #15803d)"
              : "linear-gradient(135deg, #6366f1, #4f46e5)",
            boxShadow: saved
              ? "0 4px 16px -4px rgba(34,197,94,0.25)"
              : "0 4px 16px -4px rgba(99,102,241,0.25)",
          }}
        >
          {saving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {saving ? "Sauvegarde..." : saved ? "Sauvegardé" : "Sauvegarder"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl px-4 py-3 text-sm flex items-center gap-2.5 animate-fade-in"
          style={{
            background: "rgba(239,68,68,0.06)",
            border: "1px solid rgba(239,68,68,0.15)",
            color: "#f87171",
          }}>
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {saved && (
        <div className="rounded-xl px-4 py-3 text-sm flex items-center gap-2.5 animate-fade-in"
          style={{
            background: "rgba(34,197,94,0.06)",
            border: "1px solid rgba(34,197,94,0.15)",
            color: "#4ade80",
          }}>
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          Paramètres sauvegardés avec succès
        </div>
      )}

      {/* ── Plages horaires de surveillance ── */}
      <Section
        icon={<Clock className="w-4 h-4" />}
        title="Plages horaires de surveillance"
        desc="Définir les créneaux de surveillance. Vide = surveillance permanente."
        accent="brand"
      >
        {settings.recording_periods.length === 0 && (
          <div className="text-xs text-gray-500 italic py-3 px-4 rounded-xl text-center"
            style={{
              background: "rgba(99,102,241,0.04)",
              border: "1px dashed rgba(99,102,241,0.15)",
            }}>
            Aucune plage configurée — surveillance active en permanence
          </div>
        )}

        <div className="space-y-2">
          {settings.recording_periods.map((period, idx) => (
            <div key={idx} className="flex items-center gap-3 p-2.5 rounded-xl transition-colors duration-150"
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 w-12 shrink-0 text-center">
                {idx + 1}
              </span>
              <input
                type="time"
                value={period.start}
                onChange={(e) => updatePeriod(idx, "start", e.target.value)}
                title={`Début plage ${idx + 1}`}
                className="input-field flex-1 text-center"
              />
              <div className="text-gray-400 shrink-0">
                <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
                  <path d="M14 1l5 5-5 5M0 6h19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <input
                type="time"
                value={period.end}
                onChange={(e) => updatePeriod(idx, "end", e.target.value)}
                title={`Fin plage ${idx + 1}`}
                className="input-field flex-1 text-center"
              />
              <button
                onClick={() => removePeriod(idx)}
                title="Supprimer cette plage"
                className="p-2 rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        <button
          onClick={addPeriod}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium w-full justify-center transition-all duration-200"
          style={{
            color: "#6366f1",
            border: "1px dashed rgba(99,102,241,0.25)",
            background: "rgba(99,102,241,0.04)",
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          Ajouter une plage horaire
        </button>

        <Field label="Seuil de retard">
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={0}
              max={60}
              value={settings.late_threshold_minutes}
              onChange={(e) =>
                update("late_threshold_minutes", Number(e.target.value))
              }
              title="Seuil de retard"
              className="flex-1"
              style={{ color: "#6366f1" }}
            />
            <span className="text-sm text-gray-400 font-mono w-16 text-right tabular-nums">
              {settings.late_threshold_minutes} min
            </span>
          </div>
        </Field>
      </Section>

      {/* ── Reconnaissance faciale ── */}
      <Section
        icon={<Eye className="w-4 h-4" />}
        title="Reconnaissance faciale"
        desc="Paramètres du moteur InsightFace"
        accent="cyan"
      >
        <Field label="Seuil de similarité">
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={0.1}
              max={0.9}
              step={0.05}
              value={settings.face_recognition_threshold}
              onChange={(e) =>
                update(
                  "face_recognition_threshold",
                  Number(e.target.value)
                )
              }
              title="Seuil de similarité"
              className="flex-1"
              style={{ color: "#06b6d4" }}
            />
            <span className="text-sm text-gray-400 font-mono w-12 text-right tabular-nums">
              {settings.face_recognition_threshold.toFixed(2)}
            </span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1.5">
            Plus bas = plus permissif · Plus haut = plus strict
          </p>
        </Field>
        <Field label="Intervalle de reconnaissance">
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={1}
              max={30}
              value={settings.face_recognition_interval}
              onChange={(e) =>
                update(
                  "face_recognition_interval",
                  Number(e.target.value)
                )
              }
              title="Intervalle de reconnaissance"
              className="flex-1"
              style={{ color: "#06b6d4" }}
            />
            <span className="text-sm text-gray-400 font-mono w-12 text-right tabular-nums">
              {settings.face_recognition_interval}s
            </span>
          </div>
        </Field>
      </Section>

      {/* ── Suivi de présence ── */}
      <Section
        icon={<Timer className="w-4 h-4" />}
        title="Suivi de présence"
        desc="Paramètres du tracking d'entrées/sorties"
        accent="amber"
      >
        <Field label="Timeout d'absence">
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={5}
              max={120}
              value={settings.absence_timeout_sec}
              onChange={(e) =>
                update("absence_timeout_sec", Number(e.target.value))
              }
              title="Timeout d'absence"
              className="flex-1"
              style={{ color: "#f59e0b" }}
            />
            <span className="text-sm text-gray-400 font-mono w-12 text-right tabular-nums">
              {settings.absence_timeout_sec}s
            </span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1.5">
            Durée avant de considérer une personne comme sortie
          </p>
        </Field>
      </Section>

      {/* ── Caméra ── */}
      <Section
        icon={<Camera className="w-4 h-4" />}
        title="Caméra"
        desc="Source vidéo par défaut"
        accent="emerald"
      >
        <Field label="Source caméra">
          <input
            type="text"
            value={settings.camera_source}
            onChange={(e) => update("camera_source", e.target.value)}
            placeholder="0, rtsp://..., http://..."
            className="input-field"
          />
          <p className="text-[11px] text-gray-400 mt-1.5">
            0 pour webcam · URL RTSP/HTTP pour caméra IP
          </p>
        </Field>
        <Toggle
          label="Démarrer l'inspection automatiquement"
          checked={settings.auto_start_inspection}
          onChange={(v) => update("auto_start_inspection", v)}
        />
      </Section>

      {/* ── Notifications & Export ── */}
      <Section
        icon={<Bell className="w-4 h-4" />}
        title="Notifications & Export"
        desc="Alertes et format d'exportation"
        accent="violet"
      >
        <Toggle
          label="Activer les notifications"
          checked={settings.notification_enabled}
          onChange={(v) => update("notification_enabled", v)}
        />
        <Field label="Format d'export">
          <div className="flex items-center gap-2">
            {["csv", "json", "xlsx"].map((fmt) => (
              <button
                key={fmt}
                onClick={() => update("export_format", fmt)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium transition-all duration-200 ${
                  settings.export_format === fmt
                    ? "text-white shadow-glow"
                    : "text-gray-400 hover:text-gray-300"
                }`}
                style={
                  settings.export_format === fmt
                    ? {
                        background: "linear-gradient(135deg, #6366f1, #4f46e5)",
                        border: "1px solid rgba(99,102,241,0.3)",
                      }
                    : {
                        background: "rgba(255,255,255,0.02)",
                        border: "1px solid rgba(255,255,255,0.06)",
                      }
                }
              >
                <FileDown className="w-3.5 h-3.5" />
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
        </Field>
      </Section>
    </div>
  );
}

/* ─── Reusable sub-components ─────────────────────── */

const SECTION_ACCENT: Record<string, string> = {
  brand: "rgba(99,102,241,0.5)",
  cyan: "rgba(6,182,212,0.5)",
  amber: "rgba(245,158,11,0.5)",
  emerald: "rgba(16,185,129,0.5)",
  violet: "rgba(139,92,246,0.5)",
};

function Section({
  icon,
  title,
  desc,
  accent = "brand",
  children,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  accent?: string;
  children: React.ReactNode;
}) {
  const accentColor = SECTION_ACCENT[accent] || SECTION_ACCENT.brand;
  return (
    <div className="glass-card rounded-2xl p-5 transition-all duration-200 hover:shadow-card-hover"
      style={{ borderLeft: `2px solid ${accentColor}` }}>
      <div className="flex items-center gap-2.5 mb-1">
        <span style={{ color: accentColor }}>{icon}</span>
        <h2 className="text-sm font-semibold text-gray-300 tracking-tight">{title}</h2>
      </div>
      <p className="text-[11px] text-gray-400 mb-5 ml-[26px]">{desc}</p>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[11px] font-medium text-gray-400 mb-2 uppercase tracking-wider">
        {label}
      </label>
      {children}
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex items-center justify-between w-full py-1.5 group/toggle"
    >
      <span className="text-xs text-gray-500 group-hover/toggle:text-gray-300 transition-colors">{label}</span>
      <div
        className="relative w-10 h-[22px] rounded-full transition-all duration-300"
        style={{
          background: checked
            ? "linear-gradient(135deg, #6366f1, #4f46e5)"
            : "#333",
          boxShadow: checked ? "0 0 12px -2px rgba(99,102,241,0.2)" : "none",
        }}
      >
        <div
          className={`absolute top-[3px] left-[3px] w-4 h-4 rounded-full bg-white transition-all duration-300 ${
            checked ? "translate-x-[18px]" : ""
          }`}
          style={{
            boxShadow: "0 1px 4px rgba(0,0,0,0.2)",
          }}
        />
      </div>
    </button>
  );
}
