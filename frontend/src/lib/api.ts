/* ═══════════════════════════════════════════
   API Client — Surveillance-IA
   ═══════════════════════════════════════════ */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, opts?: RequestInit): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("surv_token") : null;

  const headers: Record<string, string> = {
    ...(opts?.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!headers["Content-Type"] && !(opts?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  // Don't set Content-Type for FormData (browser sets boundary)
  if (opts?.body instanceof FormData) {
    delete headers["Content-Type"];
  }

  const res = await fetch(`${API}${path}`, { ...opts, headers });
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
