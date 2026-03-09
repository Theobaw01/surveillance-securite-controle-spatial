/* ═══════════════════════════════════════════
   API Client — Surveillance-IA
   ═══════════════════════════════════════════ */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Default admin credentials for auto-re-login on 401
const DEFAULT_USER = "admin";
const DEFAULT_PASS = "admin_surv_2024";

/** Low-level fetch (no retry). */
async function rawFetch<T>(path: string, opts?: RequestInit): Promise<Response> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("surv_token") : null;

  const headers: Record<string, string> = {
    ...(opts?.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!headers["Content-Type"] && !(opts?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (opts?.body instanceof FormData) {
    delete headers["Content-Type"];
  }

  return fetch(`${API}${path}`, { ...opts, headers });
}

/** Fetch with automatic re-login on 401. */
async function fetchAPI<T>(path: string, opts?: RequestInit): Promise<T> {
  let res = await rawFetch<T>(path, opts);

  // On 401, try to refresh the token and retry once
  if (res.status === 401 && path !== "/auth/token") {
    try {
      const loginRes = await fetch(`${API}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: DEFAULT_USER, password: DEFAULT_PASS }),
      });
      if (loginRes.ok) {
        const data = await loginRes.json();
        if (typeof window !== "undefined" && data.access_token) {
          localStorage.setItem("surv_token", data.access_token);
        }
        // Retry original request with fresh token
        res = await rawFetch<T>(path, opts);
      }
    } catch {
      // Re-login failed, fall through to error handling
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────
export async function login(username: string, password: string) {
  const data = await fetchAPI<{ access_token: string }>("/auth/token", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("surv_token", data.access_token);
  }
  return data;
}

export function logout() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("surv_token");
  }
}

export function isAuthenticated() {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("surv_token");
}

// ── Health ───────────────────────────────────────────
export function getHealth() {
  return fetchAPI<{
    status: string;
    active_streams: number;
    version: string;
  }>("/health");
}

// ── Stream ───────────────────────────────────────────
export function startStream(source = "0", cameraId = "cam_01") {
  return fetchAPI("/stream/start", {
    method: "POST",
    body: JSON.stringify({
      source,
      camera_id: cameraId,
    }),
  });
}

export function stopStream(cameraId = "cam_01") {
  return fetchAPI("/stream/stop", {
    method: "POST",
    body: JSON.stringify({ camera_id: cameraId }),
  });
}

export function getStreamStatus(cameraId = "cam_01") {
  return fetchAPI<{
    camera_id: string;
    is_running: boolean;
    fps: number;
    frames_processed: number;
  }>(`/stream/status?camera_id=${cameraId}`);
}

export function getStats(cameraId = "cam_01") {
  return fetchAPI<{
    current_occupancy: number;
    total_entries: number;
    total_exits: number;
    total_unique_persons: number;
    active_persons: number;
    fps: number;
    uptime_seconds: number;
  }>(`/stats?camera_id=${cameraId}`);
}

export function getAlerts(cameraId = "cam_01") {
  return fetchAPI<{ alerts: Array<Record<string, unknown>>; count: number }>(
    `/alerts?camera_id=${cameraId}`
  );
}

export function getEvents(cameraId = "cam_01") {
  return fetchAPI<{ events: Array<Record<string, unknown>>; count: number }>(
    `/events?camera_id=${cameraId}`
  );
}

// ── Frame live ───────────────────────────────────────
export function getLiveFrameURL(cameraId = "cam_01") {
  return `${API}/stream/frame?camera_id=${cameraId}`;
}

// ── Persons ──────────────────────────────────────────
export function getPersons() {
  return fetchAPI<{
    persons: Array<{
      person_id: string;
      nom: string;
      prenom: string;
      groupe: string;
      role: string;
      organisation: string;
      created_at: string;
    }>;
    total: number;
  }>("/persons");
}

export async function registerPerson(
  photo: File,
  nom: string,
  prenom: string,
  groupe: string,
  role: string
) {
  const form = new FormData();
  form.append("photo", photo);
  form.append("nom", nom);
  form.append("prenom", prenom);
  form.append("groupe", groupe);
  form.append("role", role);

  return fetchAPI<{
    status: string;
    person_id: string;
    face_detected: boolean;
    face_score: number;
  }>("/persons/register", { method: "POST", body: form });
}

export function deletePerson(personId: string) {
  return fetchAPI(`/persons/${personId}`, { method: "DELETE" });
}

// ── Detection ────────────────────────────────────────
export async function detectImage(image: File, confThreshold = 0.3) {
  const form = new FormData();
  form.append("image", image);
  form.append("conf_threshold", confThreshold.toString());

  return fetchAPI<{
    detections: Array<{
      bbox: number[];
      confidence: number;
      name: string | null;
      similarity: number;
    }>;
    total_persons: number;
    total_identified: number;
    processing_ms: number;
    annotated_image: string;
  }>("/detect/image", { method: "POST", body: form });
}

// ── Video Detection ──────────────────────────────────
export async function detectVideo(
  video: File,
  confThreshold = 0.3,
  frameSkip = 10
) {
  const form = new FormData();
  form.append("video", video);
  form.append("conf_threshold", confThreshold.toString());
  form.append("frame_skip", frameSkip.toString());

  return fetchAPI<{
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
  }>("/detect/video", { method: "POST", body: form });
}

// ── Attendance / Présence ────────────────────────────
export function getAttendanceToday(personId?: string) {
  const qs = personId ? `?person_id=${personId}` : "";
  return fetchAPI<{
    records: Array<Record<string, unknown>>;
    total: number;
    date: string;
  }>(`/attendance/today${qs}`);
}

export function getAttendanceLate() {
  return fetchAPI<{
    records: Array<Record<string, unknown>>;
    total: number;
    date: string;
  }>("/attendance/late");
}

export function getAttendanceAbsent() {
  return fetchAPI<{
    records: Array<Record<string, unknown>>;
    total: number;
    date: string;
  }>("/attendance/absent");
}

export function getPresenceDuration(personId?: string) {
  const qs = personId ? `?person_id=${personId}` : "";
  return fetchAPI<{
    records: Array<{
      person_id: string;
      nom: string;
      prenom: string;
      entry_time: string;
      exit_time: string | null;
      still_present: boolean;
      duration_sec: number;
      duration_formatted: string;
      total_entries: number;
      total_exits: number;
    }>;
    total: number;
    total_duration_sec: number;
    date: string;
  }>(`/attendance/presence${qs}`);
}

export function getAttendanceStats(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const qs = params.toString() ? `?${params}` : "";
  return fetchAPI<{
    date_from: string;
    date_to: string;
    total_inscrits: number;
    total_present: number;
    total_absent: number;
    total_retards: number;
    retard_moyen_min: number;
    retard_max_min: number;
    taux_presence: number;
  }>(`/attendance/stats${qs}`);
}
