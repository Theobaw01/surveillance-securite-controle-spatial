"use client";

import { useState, useRef } from "react";
import {
  Image as ImageIcon,
  Upload,
  Loader2,
  User,
  UserCheck,
  Clock,
} from "lucide-react";
import { detectImage } from "@/lib/api";

export default function DetectPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    annotated_image: string;
    total_persons: number;
    total_identified: number;
    processing_ms: number;
    detections: Array<{
      bbox: number[];
      confidence: number;
      name: string | null;
      similarity: number;
    }>;
  } | null>(null);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [confThreshold, setConfThreshold] = useState(0.3);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setPreview(URL.createObjectURL(f));
      setResult(null);
      setError("");
    }
  }

  async function handleDetect() {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const res = await detectImage(file, confThreshold);
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur détection");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <ImageIcon className="w-6 h-6" /> Détection
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Uploadez une image pour détecter &amp; identifier les personnes
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload */}
        <div className="space-y-4">
          <div
            className="bg-surface-card border-2 border-dashed border-surface-border rounded-xl p-8 text-center cursor-pointer hover:border-brand-500 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            {preview ? (
              <img
                src={preview}
                alt="Image"
                className="max-h-80 mx-auto rounded-lg object-contain"
              />
            ) : (
              <>
                <Upload className="w-12 h-12 mx-auto text-gray-500 mb-3" />
                <p className="text-sm text-gray-400">
                  Cliquez ou déposez une image
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  JPG, PNG — max 10 MB
                </p>
              </>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              onChange={handleFile}
              className="hidden"
            />
          </div>

          {/* Confidence slider */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <label className="text-xs text-gray-400 block mb-2">
              Seuil de confiance : {(confThreshold * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={confThreshold}
              onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
              className="w-full accent-brand-600"
            />
          </div>

          <button
            onClick={handleDetect}
            disabled={!file || loading}
            className="w-full py-3 bg-brand-600 text-white rounded-xl text-sm font-semibold hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analyse en cours...
              </>
            ) : (
              "Analyser l'image"
            )}
          </button>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-lg">
              {error}
            </div>
          )}
        </div>

        {/* Results */}
        <div className="space-y-4">
          {result && (
            <>
              {/* Annotated image */}
              <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-surface-border">
                  <span className="text-sm font-medium text-gray-200">
                    Résultat
                  </span>
                </div>
                <img
                  src={`data:image/jpeg;base64,${result.annotated_image}`}
                  alt="Annotated"
                  className="w-full object-contain"
                />
              </div>

              {/* Stats */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <User className="w-5 h-5 mx-auto text-blue-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {result.total_persons}
                  </p>
                  <p className="text-[11px] text-gray-400">Personnes</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <UserCheck className="w-5 h-5 mx-auto text-green-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {result.total_identified}
                  </p>
                  <p className="text-[11px] text-gray-400">Identifiées</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <Clock className="w-5 h-5 mx-auto text-purple-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {result.processing_ms.toFixed(0)}
                  </p>
                  <p className="text-[11px] text-gray-400">ms</p>
                </div>
              </div>

              {/* Detections list */}
              <div className="bg-surface-card border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">
                  Détections détaillées
                </h3>
                <div className="space-y-2">
                  {result.detections.map((det, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-surface/50 border border-surface-border"
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-2 h-2 rounded-full ${
                            det.name ? "bg-green-400" : "bg-red-400"
                          }`}
                        />
                        <span className="text-sm text-gray-200">
                          {det.name || "Inconnu"}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-400">
                        <span>
                          Conf: {(det.confidence * 100).toFixed(0)}%
                        </span>
                        {det.similarity > 0 && (
                          <span className="text-green-400">
                            Sim: {(det.similarity * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {!result && !loading && (
            <div className="bg-surface-card border border-surface-border rounded-xl p-12 text-center">
              <ImageIcon className="w-16 h-16 mx-auto text-gray-600 mb-3" />
              <p className="text-sm text-gray-500">
                Uploadez une image et cliquez &quot;Analyser&quot;
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
