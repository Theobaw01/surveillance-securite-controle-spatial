"use client";

import { useState } from "react";
import {
  Camera,
  Play,
  Square,
  Settings,
  MonitorPlay,
} from "lucide-react";
import { startStream, stopStream } from "@/lib/api";
import LiveFeed from "@/components/LiveFeed";

export default function CamerasPage() {
  const [cameras, setCameras] = useState([
    { id: "cam_01", source: "0", label: "Caméra principale", running: false },
  ]);
  const [newSource, setNewSource] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function handleStart(camId: string, source: string) {
    setLoading(camId);
    setError("");
    try {
      await startStream(source, camId);
      setCameras((prev) =>
        prev.map((c) => (c.id === camId ? { ...c, running: true } : c))
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur démarrage");
    } finally {
      setLoading(null);
    }
  }

  async function handleStop(camId: string) {
    setLoading(camId);
    setError("");
    try {
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Camera className="w-6 h-6" /> Caméras
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Gérez vos flux vidéo de surveillance
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Camera list */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
          </div>
        ))}
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
