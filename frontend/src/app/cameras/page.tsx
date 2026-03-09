"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Camera,
  Play,
  Square,
  Settings,
  MonitorPlay,
  ScanFace,
  StopCircle,
  UserCheck,
  Clock,
  LogIn,
  LogOut,
} from "lucide-react";
import {
  startStream,
  stopStream,
  getStreamStatus,
  startInspection,
  stopInspection,
  getInspectionStatus,
} from "@/lib/api";
import LiveFeed from "@/components/LiveFeed";

interface InspectionPerson {
  person_id: string;
  nom: string;
  prenom: string;
  full_name: string;
  entry_time: string;
  duration_sec: number;
  duration_formatted: string;
  similarity: number;
}

interface HistoryEntry {
  person_id: string;
  nom: string;
  prenom: string;
  entry_time: string;
  exit_time: string;
  duration_sec: number;
}

export default function CamerasPage() {
  const [cameras, setCameras] = useState([
    { id: "cam_01", source: "0", label: "Caméra principale", running: false },
  ]);
  const [newSource, setNewSource] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Inspection state
  const [inspectionActive, setInspectionActive] = useState(false);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [presentPersons, setPresentPersons] = useState<InspectionPerson[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [totalVisits, setTotalVisits] = useState(0);

  // Sync running state from backend on mount
  useEffect(() => {
    cameras.forEach((cam) => {
      getStreamStatus(cam.id)
        .then((status) => {
          if (status.is_running !== cam.running) {
            setCameras((prev) =>
              prev.map((c) =>
                c.id === cam.id ? { ...c, running: status.is_running } : c
              )
            );
          }
        })
        .catch(() => {});

      // Also check inspection status
      getInspectionStatus(cam.id)
        .then((st) => {
          if (st.active) {
            setInspectionActive(true);
            setPresentPersons(st.present_persons);
            setHistory(st.history as HistoryEntry[]);
            setTotalVisits(st.total_visits);
          }
        })
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll inspection status when active
  const pollInspection = useCallback(() => {
    if (!inspectionActive) return;
    getInspectionStatus("cam_01")
      .then((st) => {
        setPresentPersons(st.present_persons);
        setHistory(st.history as HistoryEntry[]);
        setTotalVisits(st.total_visits);
      })
      .catch(() => {});
  }, [inspectionActive]);

  useEffect(() => {
    if (!inspectionActive) return;
    pollInspection();
    const iv = setInterval(pollInspection, 2000);
    return () => clearInterval(iv);
  }, [inspectionActive, pollInspection]);

  async function handleStart(camId: string, source: string) {
    setLoading(camId);
    setError("");
    try {
      await startStream(source, camId);
      setCameras((prev) =>
        prev.map((c) => (c.id === camId ? { ...c, running: true } : c))
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      // 409 = stale stream — force stop then restart
      if (msg.includes("409") || msg.toLowerCase().includes("déjà actif")) {
        try {
          await stopStream(camId);
          await new Promise((r) => setTimeout(r, 1500));
          await startStream(source, camId);
          setCameras((prev) =>
            prev.map((c) => (c.id === camId ? { ...c, running: true } : c))
          );
          return;
        } catch (retryErr: unknown) {
          setError(retryErr instanceof Error ? retryErr.message : "Erreur redémarrage");
          return;
        }
      }
      setError(msg || "Erreur démarrage");
    } finally {
      setLoading(null);
    }
  }

  async function handleStop(camId: string) {
    setLoading(camId);
    setError("");
    try {
      // Stop inspection first if active
      if (inspectionActive) {
        await stopInspection(camId).catch(() => {});
        setInspectionActive(false);
        setPresentPersons([]);
      }
      await stopStream(camId);
      setCameras((prev) =>
        prev.map((c) => (c.id === camId ? { ...c, running: false } : c))
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur arrêt");
    } finally {
      setLoading(null);
    }
  }

  async function handleStartInspection() {
    setInspectionLoading(true);
    setError("");
    try {
      await startInspection("cam_01");
      setInspectionActive(true);
      setPresentPersons([]);
      setHistory([]);
      setTotalVisits(0);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur inspection");
    } finally {
      setInspectionLoading(false);
    }
  }

  async function handleStopInspection() {
    setInspectionLoading(true);
    setError("");
    try {
      const report = await stopInspection("cam_01");
      setInspectionActive(false);
      setHistory(report.history as HistoryEntry[]);
      setTotalVisits(report.total_visits);
      setPresentPersons([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur arrêt inspection");
    } finally {
      setInspectionLoading(false);
    }
  }

  function addCamera() {
    if (!newSource.trim()) return;
    const id = `cam_${String(cameras.length + 1).padStart(2, "0")}`;
    setCameras((prev) => [
      ...prev,
      {
        id,
        source: newSource.trim(),
        label: newLabel.trim() || id,
        running: false,
      },
    ]);
    setNewSource("");
    setNewLabel("");
  }

  function fmtDuration(sec: number) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}min`;
    return `${m}min ${s.toString().padStart(2, "0")}s`;
  }

  const cam01Running = cameras.find((c) => c.id === "cam_01")?.running ?? false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Camera className="w-6 h-6" /> Caméras
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Gérez vos flux vidéo et lancez l&apos;inspection faciale
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Camera list + inspection */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Camera feed — 2 cols */}
        <div className="lg:col-span-2 space-y-3">
          {cameras.map((cam) => (
            <div key={cam.id} className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MonitorPlay className="w-4 h-4 text-gray-400" />
                  <span className="text-sm font-medium text-gray-200">
                    {cam.label}
                  </span>
                  <span className="text-[11px] text-gray-500">
                    ({cam.source})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {cam.running ? (
                    <button
                      onClick={() => handleStop(cam.id)}
                      disabled={loading === cam.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-xs font-medium hover:bg-red-500/30 transition-colors disabled:opacity-50"
                    >
                      <Square className="w-3 h-3" />
                      Arrêter
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStart(cam.id, cam.source)}
                      disabled={loading === cam.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/20 text-green-400 rounded-lg text-xs font-medium hover:bg-green-500/30 transition-colors disabled:opacity-50"
                    >
                      <Play className="w-3 h-3" />
                      Démarrer
                    </button>
                  )}
                </div>
              </div>
              <LiveFeed cameraId={cam.id} isRunning={cam.running} />

              {/* Inspection button — only when stream is running */}
              {cam.id === "cam_01" && cam.running && (
                <div className="flex items-center gap-3">
                  {!inspectionActive ? (
                    <button
                      onClick={handleStartInspection}
                      disabled={inspectionLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors disabled:opacity-50"
                    >
                      <ScanFace className="w-4 h-4" />
                      {inspectionLoading ? "Chargement..." : "Commencer l'inspection"}
                    </button>
                  ) : (
                    <button
                      onClick={handleStopInspection}
                      disabled={inspectionLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm font-medium hover:bg-red-500/30 transition-colors disabled:opacity-50"
                    >
                      <StopCircle className="w-4 h-4" />
                      {inspectionLoading ? "Arrêt..." : "Arrêter l'inspection"}
                    </button>
                  )}
                  {inspectionActive && (
                    <span className="flex items-center gap-1 text-xs text-green-400 bg-green-500/10 px-3 py-1.5 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                      Inspection en cours
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Right panel — Présences en direct */}
        <div className="space-y-4">
          {/* Personnes présentes */}
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-green-400" />
                Personnes présentes
              </h3>
              <span className="text-xs font-mono text-brand-400 bg-brand-500/10 px-2 py-0.5 rounded-full">
                {presentPersons.length}
              </span>
            </div>
            <div className="max-h-[300px] overflow-y-auto">
              {!inspectionActive && !cam01Running && (
                <div className="p-4 text-center text-gray-500 text-sm">
                  Démarrez la caméra puis lancez l&apos;inspection
                </div>
              )}
              {cam01Running && !inspectionActive && (
                <div className="p-4 text-center text-gray-500 text-sm">
                  <ScanFace className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  Cliquez &quot;Commencer l&apos;inspection&quot; pour activer la reconnaissance faciale
                </div>
              )}
              {inspectionActive && presentPersons.length === 0 && (
                <div className="p-4 text-center text-gray-500 text-sm">
                  <ScanFace className="w-8 h-8 mx-auto mb-2 opacity-30 animate-pulse" />
                  En attente de détection...
                </div>
              )}
              {presentPersons.map((p) => (
                <div
                  key={p.person_id}
                  className="px-4 py-3 border-b border-surface-border last:border-0 flex items-center justify-between"
                >
                  <div>
                    <p className="text-sm font-medium text-white">{p.full_name}</p>
                    <p className="text-[11px] text-gray-500 flex items-center gap-1 mt-0.5">
                      <LogIn className="w-3 h-3" />
                      {p.entry_time.split(" ")[1]}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-mono text-green-400">{p.duration_formatted}</p>
                    <p className="text-[10px] text-gray-500">{(p.similarity * 100).toFixed(0)}%</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Historique des visites */}
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
                <Clock className="w-4 h-4 text-yellow-400" />
                Historique des visites
              </h3>
              <span className="text-xs font-mono text-gray-400">
                {totalVisits} visite(s)
              </span>
            </div>
            <div className="max-h-[250px] overflow-y-auto">
              {history.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">
                  Aucune visite terminée
                </div>
              ) : (
                [...history].reverse().map((h, i) => (
                  <div
                    key={`${h.person_id}-${i}`}
                    className="px-4 py-2.5 border-b border-surface-border last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-gray-200">
                        {h.prenom} {h.nom}
                      </p>
                      <p className="text-xs font-mono text-yellow-400">
                        {fmtDuration(h.duration_sec)}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-500">
                      <span className="flex items-center gap-1">
                        <LogIn className="w-3 h-3 text-green-500" />
                        {h.entry_time?.split(" ")[1]}
                      </span>
                      <span className="flex items-center gap-1">
                        <LogOut className="w-3 h-3 text-red-400" />
                        {h.exit_time?.split(" ")[1]}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Add camera */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2 mb-4">
          <Settings className="w-4 h-4" />
          Ajouter une caméra
        </h3>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Source (0, rtsp://..., video.mp4)"
            value={newSource}
            onChange={(e) => setNewSource(e.target.value)}
            className="flex-1 bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
          />
          <input
            type="text"
            placeholder="Nom (optionnel)"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="w-48 bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
          />
          <button
            onClick={addCamera}
            className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors"
          >
            Ajouter
          </button>
        </div>
        <p className="text-[11px] text-gray-500 mt-2">
          Source : <code className="text-gray-400">0</code> = webcam,{" "}
          <code className="text-gray-400">rtsp://...</code> = caméra IP,{" "}
          <code className="text-gray-400">video.mp4</code> = fichier
        </p>
      </div>
    </div>
  );
}
