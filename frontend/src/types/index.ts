/* ═══════════════════════════════════════════
   Types TypeScript — Surveillance-IA
   ═══════════════════════════════════════════ */

export interface StreamStats {
  camera_id: string;
  is_running: boolean;
  frames_processed: number;
  fps: number;
  current_occupancy: number;
  total_entries: number;
  total_exits: number;
  total_unique_persons: number;
  active_persons: number;
  counts_by_line: Record<string, { IN: number; OUT: number }>;
  hourly_histogram: Record<string, number>;
  uptime_seconds: number;
}

export interface Person {
  person_id: string;
  nom: string;
  prenom: string;
  groupe: string;
  role: string;
  organisation: string;
  created_at: string;
}

export interface Detection {
  bbox: [number, number, number, number];
  confidence: number;
  name: string | null;
  similarity: number;
  person_id?: string;
}

export interface DetectionResult {
  detections: Detection[];
  total_persons: number;
  total_identified: number;
  processing_ms: number;
  annotated_image: string;
}

export interface Alert {
  id: number;
  person_id: number;
  alert_type: string;
  message: string;
  datetime: string;
  acknowledged: boolean;
}

export interface WsMessage {
  type: "stats" | "update";
  camera_id: string;
  data?: StreamStats;
  timestamp: number;
  // update fields
  counts?: Record<string, unknown>;
  occupancy?: number;
  total_entries?: number;
  total_exits?: number;
  fps?: number;
  frames?: number;
  active_sessions?: number;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  active_streams: number;
}
