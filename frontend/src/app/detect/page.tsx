"use client";

import { useState, useRef } from "react";
import {
  Image as ImageIcon,
  Upload,
  Loader2,
  User,
  UserCheck,
  Clock,
  Video,
  Timer,
  Eye,
} from "lucide-react";
import { detectImage, detectVideo } from "@/lib/api";

type Mode = "image" | "video";

type ImageResult = {
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
};

type VideoResult = {
  video_info: {
    filename: string;
    fps: number;
    total_frames: number;
    duration_sec: number;
    duration_formatted: string;
    frames_processed: number;
    frame_skip: number;
  };
  presence: Array<{
    person_id: string;
    nom: string;
    prenom: string;
    name: string;
    first_seen_sec: number;
    last_seen_sec: number;
    duration_sec: number;
    duration_formatted: string;
    detections_count: number;
    avg_similarity: number;
    best_similarity: number;
    snapshot: string | null;
  }>;
  total_persons_identified: number;
  total_detections: number;
  unknown_detections: number;
  processing_ms: number;
  annotated_keyframe: string | null;
};

export default function DetectPage() {
  const [mode, setMode] = useState<Mode>("image");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [imageResult, setImageResult] = useState<ImageResult | null>(null);
  const [videoResult, setVideoResult] = useState<VideoResult | null>(null);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [confThreshold, setConfThreshold] = useState(0.3);
  const [frameSkip, setFrameSkip] = useState(10);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setImageResult(null);
      setVideoResult(null);
      setError("");

      if (f.type.startsWith("video/")) {
        setMode("video");
        setPreview(null); // no thumbnail for video
      } else {
        setMode("image");
        setPreview(URL.createObjectURL(f));
      }
    }
  }

  async function handleDetect() {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      if (mode === "video") {
        const res = await detectVideo(file, confThreshold, frameSkip);
        setVideoResult(res);
      } else {
        const res = await detectImage(file, confThreshold);
        setImageResult(res);
      }
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
          <ImageIcon className="w-6 h-6" /> Détection &amp; Présence
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Uploadez une image ou une vidéo pour détecter, identifier et mesurer
          le temps de présence
        </p>
      </div>

      {/* Mode selector */}
      <div className="flex gap-2">
        <button
          onClick={() => {
            setMode("image");
            setFile(null);
            setPreview(null);
            setImageResult(null);
            setVideoResult(null);
            setError("");
          }}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === "image"
              ? "bg-brand-600 text-white"
              : "bg-surface-card text-gray-400 border border-surface-border hover:text-white"
          }`}
        >
          <ImageIcon className="w-4 h-4" /> Image
        </button>
        <button
          onClick={() => {
            setMode("video");
            setFile(null);
            setPreview(null);
            setImageResult(null);
            setVideoResult(null);
            setError("");
          }}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === "video"
              ? "bg-brand-600 text-white"
              : "bg-surface-card text-gray-400 border border-surface-border hover:text-white"
          }`}
        >
          <Video className="w-4 h-4" /> Vidéo
        </button>
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
                alt="Preview"
                className="max-h-80 mx-auto rounded-lg object-contain"
              />
            ) : file && mode === "video" ? (
              <div className="py-4">
                <Video className="w-16 h-16 mx-auto text-brand-400 mb-3" />
                <p className="text-sm text-gray-200 font-medium">
                  {file.name}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </p>
              </div>
            ) : (
              <>
                <Upload className="w-12 h-12 mx-auto text-gray-500 mb-3" />
                <p className="text-sm text-gray-400">
                  {mode === "video"
                    ? "Cliquez ou déposez une vidéo"
                    : "Cliquez ou déposez une image"}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {mode === "video"
                    ? "MP4, AVI, MOV, MKV"
                    : "JPG, PNG — max 10 MB"}
                </p>
              </>
            )}
            <input
              ref={fileRef}
              type="file"
              accept={
                mode === "video"
                  ? "video/mp4,video/avi,video/quicktime,video/x-matroska,video/*"
                  : "image/*"
              }
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

          {/* Frame skip (video only) */}
          {mode === "video" && (
            <div className="bg-surface-card border border-surface-border rounded-xl p-4">
              <label className="text-xs text-gray-400 block mb-2">
                Traiter 1 frame sur {frameSkip}{" "}
                <span className="text-gray-500">
                  (↓ = plus précis mais plus lent)
                </span>
              </label>
              <input
                type="range"
                min="1"
                max="30"
                step="1"
                value={frameSkip}
                onChange={(e) => setFrameSkip(parseInt(e.target.value))}
                className="w-full accent-brand-600"
              />
            </div>
          )}

          <button
            onClick={handleDetect}
            disabled={!file || loading}
            className="w-full py-3 bg-brand-600 text-white rounded-xl text-sm font-semibold hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {mode === "video"
                  ? "Analyse vidéo en cours… (peut prendre du temps)"
                  : "Analyse en cours..."}
              </>
            ) : mode === "video" ? (
              <>
                <Video className="w-4 h-4" /> Analyser la vidéo
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

        {/* ── Results Panel ── */}
        <div className="space-y-4">
          {/* ══ IMAGE RESULTS ══ */}
          {imageResult && (
            <>
              <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-surface-border">
                  <span className="text-sm font-medium text-gray-200">
                    Résultat
                  </span>
                </div>
                <img
                  src={`data:image/jpeg;base64,${imageResult.annotated_image}`}
                  alt="Annotated"
                  className="w-full object-contain"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <User className="w-5 h-5 mx-auto text-blue-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {imageResult.total_persons}
                  </p>
                  <p className="text-[11px] text-gray-400">Personnes</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <UserCheck className="w-5 h-5 mx-auto text-green-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {imageResult.total_identified}
                  </p>
                  <p className="text-[11px] text-gray-400">Identifiées</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <Clock className="w-5 h-5 mx-auto text-purple-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {imageResult.processing_ms.toFixed(0)}
                  </p>
                  <p className="text-[11px] text-gray-400">ms</p>
                </div>
              </div>

              <div className="bg-surface-card border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">
                  Détections détaillées
                </h3>
                <div className="space-y-2">
                  {imageResult.detections.map((det, i) => (
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

          {/* ══ VIDEO RESULTS ══ */}
          {videoResult && (
            <>
              {/* Video info */}
              <div className="bg-surface-card border border-surface-border rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                  <Video className="w-4 h-4 text-brand-400" />
                  Infos vidéo
                </h3>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="text-gray-500">Durée</div>
                  <div className="text-gray-200">
                    {videoResult.video_info.duration_formatted}
                  </div>
                  <div className="text-gray-500">FPS</div>
                  <div className="text-gray-200">
                    {videoResult.video_info.fps}
                  </div>
                  <div className="text-gray-500">Frames traitées</div>
                  <div className="text-gray-200">
                    {videoResult.video_info.frames_processed} /{" "}
                    {videoResult.video_info.total_frames}
                  </div>
                  <div className="text-gray-500">Temps de traitement</div>
                  <div className="text-gray-200">
                    {(videoResult.processing_ms / 1000).toFixed(1)}s
                  </div>
                </div>
              </div>

              {/* Stats cards */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <UserCheck className="w-5 h-5 mx-auto text-green-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {videoResult.total_persons_identified}
                  </p>
                  <p className="text-[11px] text-gray-400">Identifiées</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <Eye className="w-5 h-5 mx-auto text-blue-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {videoResult.total_detections}
                  </p>
                  <p className="text-[11px] text-gray-400">Détections</p>
                </div>
                <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-center">
                  <User className="w-5 h-5 mx-auto text-orange-400 mb-1" />
                  <p className="text-xl font-bold text-white">
                    {videoResult.unknown_detections}
                  </p>
                  <p className="text-[11px] text-gray-400">Inconnus</p>
                </div>
              </div>

              {/* Annotated keyframe */}
              {videoResult.annotated_keyframe && (
                <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-surface-border">
                    <span className="text-sm font-medium text-gray-200">
                      Frame clé (plus de détections)
                    </span>
                  </div>
                  <img
                    src={`data:image/jpeg;base64,${videoResult.annotated_keyframe}`}
                    alt="Keyframe"
                    className="w-full object-contain"
                  />
                </div>
              )}

              {/* ══ PRESENCE TABLE ══ */}
              {videoResult.presence.length > 0 && (
                <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-surface-border flex items-center gap-2">
                    <Timer className="w-4 h-4 text-brand-400" />
                    <span className="text-sm font-semibold text-gray-200">
                      Temps de présence
                    </span>
                  </div>
                  <div className="divide-y divide-surface-border">
                    {videoResult.presence.map((p) => (
                      <div
                        key={p.person_id}
                        className="flex items-center gap-4 px-4 py-3"
                      >
                        {/* Snapshot */}
                        {p.snapshot ? (
                          <img
                            src={`data:image/jpeg;base64,${p.snapshot}`}
                            alt={p.name}
                            className="w-12 h-12 rounded-lg object-cover border border-surface-border"
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-lg bg-surface border border-surface-border flex items-center justify-center">
                            <User className="w-5 h-5 text-gray-500" />
                          </div>
                        )}

                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">
                            {p.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            Vu {p.detections_count} fois — Sim moy:{" "}
                            {(p.avg_similarity * 100).toFixed(0)}%
                          </p>
                        </div>

                        {/* Duration */}
                        <div className="text-right shrink-0">
                          <p className="text-lg font-bold text-brand-300">
                            {p.duration_formatted}
                          </p>
                          <p className="text-[10px] text-gray-500">
                            {_fmtSec(p.first_seen_sec)} →{" "}
                            {_fmtSec(p.last_seen_sec)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {videoResult.presence.length === 0 && (
                <div className="bg-surface-card border border-surface-border rounded-xl p-8 text-center">
                  <User className="w-12 h-12 mx-auto text-gray-600 mb-2" />
                  <p className="text-sm text-gray-500">
                    Aucune personne identifiée dans la vidéo.
                    <br />
                    Vérifiez que les personnes sont bien enregistrées.
                  </p>
                </div>
              )}
            </>
          )}

          {/* Empty state */}
          {!imageResult && !videoResult && !loading && (
            <div className="bg-surface-card border border-surface-border rounded-xl p-12 text-center">
              {mode === "video" ? (
                <>
                  <Video className="w-16 h-16 mx-auto text-gray-600 mb-3" />
                  <p className="text-sm text-gray-500">
                    Uploadez une vidéo pour analyser le temps de présence
                  </p>
                </>
              ) : (
                <>
                  <ImageIcon className="w-16 h-16 mx-auto text-gray-600 mb-3" />
                  <p className="text-sm text-gray-500">
                    Uploadez une image et cliquez &quot;Analyser&quot;
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Format seconds as MM:SS */
function _fmtSec(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
