/* ═══════════════════════════════════════════
   WebSocket Hook — Temps réel
   ═══════════════════════════════════════════ */
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WsMessage, StreamStats } from "@/types";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState<StreamStats | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    try {
      ws.current = new WebSocket(WS_URL);

      ws.current.onopen = () => {
        setConnected(true);
        console.log("🔌 WebSocket connecté");
      };

      ws.current.onmessage = (evt) => {
        try {
          const msg: WsMessage = JSON.parse(evt.data);
          if (msg.type === "stats" && msg.data) {
            setStats(msg.data);
          } else if (msg.type === "update") {
            setStats((prev) =>
              prev
                ? {
                    ...prev,
                    current_occupancy: msg.occupancy ?? prev.current_occupancy,
                    total_entries: msg.total_entries ?? prev.total_entries,
                    total_exits: msg.total_exits ?? prev.total_exits,
                    fps: msg.fps ?? prev.fps,
                    frames_processed: msg.frames ?? prev.frames_processed,
                    active_persons:
                      msg.active_sessions ?? prev.active_persons,
                  }
                : null
            );
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.current.onclose = () => {
        setConnected(false);
        console.log("🔌 WebSocket déconnecté — reconnexion dans 3s");
        reconnectTimeout.current = setTimeout(connect, 3000);
      };

      ws.current.onerror = () => {
        ws.current?.close();
      };
    } catch {
      reconnectTimeout.current = setTimeout(connect, 3000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      ws.current?.close();
    };
  }, [connect]);

  return { connected, stats };
}
