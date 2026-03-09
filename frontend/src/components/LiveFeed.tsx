"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, RefreshCw, Loader2 } from "lucide-react";
import { getLiveFrameURL } from "@/lib/api";

interface Props {
  cameraId?: string;
  isRunning?: boolean;
}

export default function LiveFeed({ cameraId = "cam_01", isRunning = false }: Props) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [error, setError] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const failCountRef = useRef(0);
  const MAX_RETRIES = 15; // ~3s at 200ms interval before showing error

  useEffect(() => {
    if (!isRunning) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setError(false);
      setConnecting(false);
      failCountRef.current = 0;
      return;
    }

    // Starting — show connecting state
    setConnecting(true);
    setError(false);
    failCountRef.current = 0;

    const refresh = () => {
      if (imgRef.current) {
        const url = getLiveFrameURL(cameraId) + `&t=${Date.now()}`;
        const img = new Image();
        img.onload = () => {
          if (imgRef.current) {
            imgRef.current.src = url;
            setError(false);
            setConnecting(false);
            failCountRef.current = 0;
          }
        };
        img.onerror = () => {
          failCountRef.current += 1;
          if (failCountRef.current >= MAX_RETRIES) {
            setError(true);
            setConnecting(false);
          }
        };
        img.src = url;
      }
    };

    refresh();
    intervalRef.current = setInterval(refresh, 200);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRunning, cameraId]);

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Camera className="w-4 h-4 text-green-400" />
          ) : (
            <CameraOff className="w-4 h-4 text-gray-500" />
          )}
          <span className="text-sm font-medium text-gray-200">
            {cameraId}
          </span>
          {isRunning && !error && !connecting && (
            <span className="flex items-center gap-1 text-[10px] text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse-green" />
              LIVE
            </span>
          )}
          {connecting && (
            <span className="flex items-center gap-1 text-[10px] text-yellow-400 bg-yellow-500/10 px-2 py-0.5 rounded-full">
              <Loader2 className="w-3 h-3 animate-spin" />
              Connexion...
            </span>
          )}
        </div>
        {isRunning && (
          <button
            className="text-gray-400 hover:text-gray-200 transition-colors"
            title="Rafraîchir"
            onClick={() => {
              failCountRef.current = 0;
              setError(false);
              setConnecting(true);
              if (imgRef.current) {
                imgRef.current.src =
                  getLiveFrameURL(cameraId) + `&t=${Date.now()}`;
              }
            }}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="relative aspect-video bg-black flex items-center justify-center">
        {isRunning && !error ? (
          <>
            <img
              ref={imgRef}
              alt="Live feed"
              className={`w-full h-full object-contain ${connecting ? "opacity-0" : ""}`}
            />
            {connecting && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center text-gray-400">
                  <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-50" />
                  <p className="text-sm">Connexion au flux...</p>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-center text-gray-500">
            <CameraOff className="w-12 h-12 mx-auto mb-2 opacity-30" />
            <p className="text-sm">
              {error ? "Erreur de connexion" : "Aucun flux actif"}
            </p>
            <p className="text-xs mt-1 text-gray-600">
              Démarrez une caméra depuis l&apos;onglet Caméras
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
