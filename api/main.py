"""
═══════════════════════════════════════════════════════════════
MODULE 9 — API FastAPI + WebSockets (Surveillance-IA)
═══════════════════════════════════════════════════════════════
- POST /stream/start    → Démarrer le flux vidéo
- POST /stream/stop     → Arrêter le flux vidéo
- GET  /stats           → Statistiques temps réel
- GET  /alerts          → Alertes actives
- GET  /report/{date}   → Rapport quotidien
- WS   /ws              → WebSocket temps réel (frames + events)
- JWT Authentication
- Documentation Swagger auto-générée
═══════════════════════════════════════════════════════════════
"""

import os
import time
import json
import asyncio
import logging
import threading
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Depends,
    Query,
    status,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "surveillance-ia-secret-key-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
DEFAULT_MODEL_PATH = os.getenv("MODEL_PATH", "yolov8n.pt")


# ═══════════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS
# ═══════════════════════════════════════════════════════════════

class StreamStartRequest(BaseModel):
    """Requête de démarrage de flux."""
    source: str = Field(
        default="0",
        description="Source vidéo : chemin fichier, URL RTSP, ou '0' pour webcam",
    )
    camera_id: str = Field(default="cam_01")
    model_path: str = Field(default=DEFAULT_MODEL_PATH)
    conf_threshold: float = Field(default=0.3, ge=0.1, le=0.95)
    counting_line_y: Optional[int] = Field(
        default=None,
        description="Position Y de la ligne de comptage (None = milieu)",
    )

class StreamStopRequest(BaseModel):
    """Requête d'arrêt de flux."""
    camera_id: str = Field(default="cam_01")

class StreamStatus(BaseModel):
    """Statut d'un flux."""
    camera_id: str
    is_running: bool
    source: str = ""
    frames_processed: int = 0
    fps: float = 0.0
    start_time: Optional[str] = None

class StatsResponse(BaseModel):
    """Statistiques temps réel."""
    current_occupancy: int = 0
    total_entries: int = 0
    total_exits: int = 0
    total_unique_persons: int = 0
    active_persons: int = 0
    fps: float = 0.0
    uptime_seconds: float = 0.0
    counts_by_line: Dict = {}
    hourly_histogram: Dict = {}

class AlertResponse(BaseModel):
    """Réponse d'alerte."""
    id: int = 0
    person_id: int = 0
    alert_type: str = ""
    message: str = ""
    datetime: str = ""
    acknowledged: bool = False

class TokenRequest(BaseModel):
    """Requête de token JWT."""
    username: str
    password: str

class TokenResponse(BaseModel):
    """Réponse de token JWT."""
    access_token: str
    token_type: str = "bearer"


# ═══════════════════════════════════════════════════════════════
# JWT AUTHENTICATION
# ═══════════════════════════════════════════════════════════════

class AuthManager:
    """Gestionnaire d'authentification JWT."""

    # Utilisateurs par défaut (en production, utiliser une DB)
    USERS = {
        "admin": {
            "password": "admin_surv_2024",
            "role": "admin",
        },
        "operator": {
            "password": "operator_surv_2024",
            "role": "operator",
        },
    }

    @staticmethod
    def create_token(username: str) -> str:
        """Crée un token JWT."""
        try:
            from jose import jwt
        except ImportError:
            # Fallback si python-jose non installé
            import hashlib
            token = hashlib.sha256(
                f"{username}:{SECRET_KEY}:{time.time()}".encode()
            ).hexdigest()
            return token

        payload = {
            "sub": username,
            "exp": datetime.utcnow() + timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            ),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[str]:
        """Vérifie un token JWT. Retourne le username ou None."""
        try:
            from jose import jwt
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload.get("sub")
        except Exception:
            return None

    @classmethod
    def authenticate(cls, username: str, password: str) -> Optional[str]:
        """Authentifie et retourne un token."""
        user = cls.USERS.get(username)
        if user and user["password"] == password:
            return cls.create_token(username)
        return None


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Dépendance FastAPI pour l'authentification."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
        )
    username = AuthManager.verify_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        )
    return username


# ═══════════════════════════════════════════════════════════════
# STREAM MANAGER (gestion des flux vidéo)
# ═══════════════════════════════════════════════════════════════

class StreamManager:
    """Gère les flux vidéo actifs et les composants de surveillance."""

    def __init__(self):
        self._streams: Dict[str, Dict] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._connected_ws: List[WebSocket] = []
        # Inspection state
        self._inspection_active: Dict[str, bool] = {}
        self._inspection_data: Dict[str, Dict] = {}
        self._face_app = None
        self._face_db = None
        self._ABSENCE_TIMEOUT = 20.0  # seconds before marking exit

    def _init_face_recognition(self):
        """Lazy-load InsightFace et FaceDatabase (réutilise routes_persons si possible)."""
        if self._face_app is not None and self._face_db is not None:
            logger.info("✅ Face recog déjà initialisé (cached)")
            return True

        logger.info("🔧 Initialisation reconnaissance faciale...")

        # Réutiliser les composants depuis routes_persons (pré-initialisés au démarrage)
        try:
            import api.routes_persons as rp
            if rp._face_app is None or rp._face_db is None:
                logger.info("🔧 Appel init_components() depuis routes_persons...")
                rp.init_components()
            
            if rp._face_app is not None:
                self._face_app = rp._face_app
                logger.info("✅ InsightFace réutilisé depuis routes_persons")
            else:
                logger.error("❌ InsightFace None dans routes_persons")
                
            if rp._face_db is not None:
                self._face_db = rp._face_db
                logger.info(f"✅ FaceDB réutilisé depuis routes_persons ({len(rp._face_db._persons_cache)} personne(s))")
            else:
                logger.error("❌ FaceDB None dans routes_persons")
                
            if self._face_app and self._face_db:
                return True
        except Exception as e:
            logger.warning(f"Erreur import routes_persons: {e}")

        # Fallback: initialiser nos propres composants
        if not self._face_app:
            try:
                from insightface.app import FaceAnalysis
                self._face_app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                self._face_app.prepare(ctx_id=0, det_size=(640, 640))
                logger.info("✅ InsightFace chargé pour inspection (fallback)")
            except Exception as e:
                logger.error(f"InsightFace non disponible : {e}")
                return False

        if not self._face_db:
            try:
                from src.face_recognition import FaceDatabase
                db_path = os.getenv("FACE_DB_PATH", "data/faces.db")
                self._face_db = FaceDatabase(db_path=db_path)
                logger.info(f"✅ FaceDatabase pour inspection (fallback): {db_path}")
            except Exception as e:
                logger.error(f"FaceDatabase non disponible : {e}")
                return False
                
        return self._face_app is not None and self._face_db is not None

    def start_inspection(self, camera_id: str) -> bool:
        """Active le mode inspection sur un flux actif."""
        if camera_id not in self._streams:
            return False
        if not self._init_face_recognition():
            return False
        self._inspection_active[camera_id] = True
        self._inspection_data[camera_id] = {
            "started_at": datetime.now().isoformat(),
            "present_persons": {},  # person_id -> {name, entry_time, last_seen, ...}
            "history": [],          # completed visits (entry+exit)
        }
        logger.info(f"🔍 Inspection démarrée sur {camera_id}")
        return True

    def stop_inspection(self, camera_id: str) -> Dict:
        """Arrête le mode inspection et retourne le rapport."""
        self._inspection_active[camera_id] = False
        data = self._inspection_data.get(camera_id, {})

        # Marquer les personnes encore présentes comme sorties
        now = time.time()
        for pid, info in list(data.get("present_persons", {}).items()):
            dt_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
            info["exit_time"] = dt_str
            info["exit_ts"] = now
            info["duration_sec"] = now - info["entry_ts"]
            data["history"].append(dict(info))
            # Enregistrer la sortie en DB
            if self._face_db:
                self._face_db.record_attendance(pid, "exit", info.get("similarity", 0), camera_id)

        present_copy = dict(data.get("present_persons", {}))
        data["present_persons"] = {}

        logger.info(f"🔍 Inspection arrêtée sur {camera_id}")
        return {
            "camera_id": camera_id,
            "started_at": data.get("started_at"),
            "stopped_at": datetime.now().isoformat(),
            "total_visits": len(data.get("history", [])),
            "history": data.get("history", []),
        }

    def get_inspection_status(self, camera_id: str) -> Dict:
        """Retourne l'état actuel de l'inspection."""
        active = self._inspection_active.get(camera_id, False)
        data = self._inspection_data.get(camera_id, {})
        present = data.get("present_persons", {})

        persons_list = []
        for pid, info in present.items():
            duration = time.time() - info["entry_ts"]
            h = int(duration // 3600)
            m = int((duration % 3600) // 60)
            s = int(duration % 60)
            dur_fmt = f"{h}h {m:02d}min {s:02d}s" if h else f"{m}min {s:02d}s"
            persons_list.append({
                "person_id": pid,
                "nom": info["nom"],
                "prenom": info["prenom"],
                "full_name": f"{info['prenom']} {info['nom']}",
                "entry_time": info["entry_time"],
                "duration_sec": round(duration, 1),
                "duration_formatted": dur_fmt,
                "similarity": info.get("similarity", 0),
            })

        return {
            "active": active,
            "camera_id": camera_id,
            "started_at": data.get("started_at"),
            "present_count": len(present),
            "present_persons": persons_list,
            "total_visits": len(data.get("history", [])),
            "history": data.get("history", []),
        }

    def _run_face_recognition(self, frame: np.ndarray, camera_id: str):
        """Exécute la reconnaissance faciale et met à jour les entrées/sorties."""
        if not self._face_app or not self._face_db:
            logger.warning(f"⚠️ Face recog skipped: face_app={self._face_app is not None}, face_db={self._face_db is not None}")
            return [], frame

        data = self._inspection_data.get(camera_id, {})
        present = data.get("present_persons", {})
        now = time.time()

        # Détecter les visages
        faces = self._face_app.get(frame)
        if faces:
            logger.debug(f"👁️ Faces détectées: {len(faces)} (camera={camera_id})")
        recognized_this_frame = set()

        for face in faces:
            if face.embedding is None:
                continue

            # Identifier via FaceDatabase
            result = self._face_db.identify(face.embedding, threshold=0.4)
            logger.debug(f"🔎 Identify result: {result}")
            if result is None:
                # Inconnu — dessiner cadre gris
                bbox = face.bbox.astype(int)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (128, 128, 128), 2)
                cv2.putText(frame, "Inconnu", (bbox[0], bbox[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)
                continue

            pid = result["person_id"]
            nom = result["nom"]
            prenom = result["prenom"]
            sim = result.get("similarity", 0)
            recognized_this_frame.add(pid)

            # Dessiner cadre vert + nom
            bbox = face.bbox.astype(int)
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            label = f"{prenom} {nom} ({sim:.0%})"
            # Fond noir pour le texte
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(frame, (bbox[0], bbox[1] - th - 10), (bbox[0] + tw, bbox[1]), (0, 0, 0), -1)
            cv2.putText(frame, label, (bbox[0], bbox[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Nouvelle entrée ?
            if pid not in present:
                dt_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                present[pid] = {
                    "person_id": pid,
                    "nom": nom,
                    "prenom": prenom,
                    "entry_time": dt_str,
                    "entry_ts": now,
                    "last_seen": now,
                    "similarity": sim,
                }
                # Enregistrer l'entrée en DB
                self._face_db.record_attendance(pid, "entry", sim, camera_id)
                logger.info(f"🟢 ENTRÉE : {prenom} {nom} à {dt_str}")
            else:
                present[pid]["last_seen"] = now
                if sim > present[pid].get("similarity", 0):
                    present[pid]["similarity"] = sim

        # Vérifier les personnes non vues depuis > ABSENCE_TIMEOUT → sortie
        for pid in list(present.keys()):
            if pid not in recognized_this_frame:
                last = present[pid]["last_seen"]
                if now - last >= self._ABSENCE_TIMEOUT:
                    dt_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                    info = present.pop(pid)
                    info["exit_time"] = dt_str
                    info["exit_ts"] = now
                    info["duration_sec"] = now - info["entry_ts"]
                    data.setdefault("history", []).append(dict(info))
                    # Enregistrer la sortie en DB
                    self._face_db.record_attendance(pid, "exit", info.get("similarity", 0), camera_id)
                    logger.info(f"🔴 SORTIE : {info['prenom']} {info['nom']} à {dt_str} (absent {self._ABSENCE_TIMEOUT}s)")

        # Overlay : panneau des personnes présentes
        if present:
            y_off = 30
            cv2.rectangle(frame, (5, 5), (320, 25 + len(present) * 28), (0, 0, 0), -1)
            cv2.putText(frame, f"Presents: {len(present)}", (10, y_off),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            for info in present.values():
                y_off += 28
                dur = now - info["entry_ts"]
                m = int(dur // 60)
                s = int(dur % 60)
                txt = f"  {info['prenom']} {info['nom']} - {m}:{s:02d}"
                cv2.putText(frame, txt, (10, y_off),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        return list(recognized_this_frame), frame

    def start_stream(
        self,
        camera_id: str,
        source: str,
        model_path: str,
        conf_threshold: float = 0.3,
        counting_line_y: Optional[int] = None,
    ) -> bool:
        """Démarre un flux de surveillance."""
        if camera_id in self._streams:
            existing = self._streams[camera_id]
            thread = existing.get("thread")
            is_running = existing.get("is_running", False)
            thread_alive = thread is not None and thread.is_alive()

            # Si le flux est réellement actif (flag + thread vivant)
            if is_running and thread_alive:
                logger.warning(f"Flux déjà actif : {camera_id}")
                return False

            # Thread mort ou flux arrêté → nettoyer et relancer
            logger.info(f"♻️ Nettoyage ancien flux (running={is_running}, alive={thread_alive}) : {camera_id}")
            old_event = self._stop_events.pop(camera_id, None)
            if old_event:
                old_event.set()
            self._streams.pop(camera_id, None)

        try:
            from src.tracker import PersonTracker
            from src.counter import PersonCounter
            from src.timer import PresenceTimer
        except ImportError as e:
            logger.error(f"Import error: {e}")
            raise HTTPException(500, f"Module introuvable : {e}")

        # Initialiser les composants
        tracker = PersonTracker(
            model_path=model_path,
            conf_threshold=conf_threshold,
        )
        counter = PersonCounter()
        timer = PresenceTimer(
            absence_timeout=10.0,
            alert_thresholds=[300, 600, 1800],
        )

        # Ajouter ligne de comptage par défaut
        cap = cv2.VideoCapture(
            int(source) if source.isdigit() else source
        )
        if not cap.isOpened():
            raise HTTPException(400, f"Impossible d'ouvrir : {source}")

        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        cap.release()

        line_y = counting_line_y or height // 2
        counter.add_horizontal_line("Ligne principale", line_y, 0, width)

        stop_event = threading.Event()
        self._stop_events[camera_id] = stop_event

        self._streams[camera_id] = {
            "source": source,
            "model_path": model_path,
            "tracker": tracker,
            "counter": counter,
            "timer": timer,
            "is_running": True,
            "frames_processed": 0,
            "fps": 0.0,
            "start_time": datetime.now(),
            "latest_frame": None,
        }

        # Lancer le thread de traitement
        thread = threading.Thread(
            target=self._process_stream,
            args=(camera_id, source, stop_event),
            daemon=True,
        )
        thread.start()
        self._streams[camera_id]["thread"] = thread

        logger.info(f"✅ Flux démarré : {camera_id} → {source}")
        return True

    def stop_stream(self, camera_id: str) -> bool:
        """Arrête un flux de surveillance."""
        if camera_id not in self._streams:
            return False

        stop_evt = self._stop_events.get(camera_id)
        if stop_evt:
            stop_evt.set()
        self._streams[camera_id]["is_running"] = False

        # Nettoyer pour permettre le redémarrage
        import time as _t
        def _cleanup():
            _t.sleep(2)  # laisser le thread se terminer
            self._streams.pop(camera_id, None)
            self._stop_events.pop(camera_id, None)
            logger.info(f"🧹 Flux {camera_id} nettoyé")
        threading.Thread(target=_cleanup, daemon=True).start()

        logger.info(f"⏹️ Flux arrêté : {camera_id}")
        return True

    def _process_stream(
        self,
        camera_id: str,
        source: str,
        stop_event: threading.Event,
    ) -> None:
        """Thread de traitement du flux vidéo."""
        stream = self._streams[camera_id]
        tracker = stream["tracker"]
        counter = stream["counter"]
        timer = stream["timer"]

        cap = cv2.VideoCapture(
            int(source) if source.isdigit() else source
        )

        start_time = time.time()
        frame_count = 0
        face_recog_interval = 5  # Run face recog every N frames (performance)

        try:
            while not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    # Fin de vidéo → reboucler ou attendre
                    if source.isdigit():
                        time.sleep(0.01)
                        continue
                    break

                # 1. Tracking
                tracking_result = tracker.track_frame(frame, draw=True)

                # 2. Comptage
                events = counter.update(tracking_result)

                # 3. Chronomètre
                active_ids = [
                    p.track_id for p in tracking_result.persons
                    if p.track_id >= 0
                ]
                alerts = timer.update(active_ids)

                # 4. Overlay compteur
                if tracking_result.annotated_frame is not None:
                    annotated = counter.draw_overlay(
                        tracking_result.annotated_frame
                    )
                else:
                    annotated = frame.copy()

                # 5. Face recognition (mode inspection)
                if self._inspection_active.get(camera_id, False):
                    if frame_count % face_recog_interval == 0:
                        try:
                            _, annotated = self._run_face_recognition(annotated, camera_id)
                        except Exception as e:
                            logger.error(f"Erreur reconnaissance faciale: {e}")
                    else:
                        # Même sans recog cette frame, vérifier les absences
                        now = time.time()
                        data = self._inspection_data.get(camera_id, {})
                        present = data.get("present_persons", {})
                        for pid in list(present.keys()):
                            if now - present[pid]["last_seen"] >= self._ABSENCE_TIMEOUT:
                                dt_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                                info = present.pop(pid)
                                info["exit_time"] = dt_str
                                info["exit_ts"] = now
                                info["duration_sec"] = now - info["entry_ts"]
                                data.setdefault("history", []).append(dict(info))
                                if self._face_db:
                                    self._face_db.record_attendance(pid, "exit", info.get("similarity", 0), camera_id)
                                logger.info(f"🔴 SORTIE : {info['prenom']} {info['nom']} à {dt_str}")

                        # Redessiner le panneau des présents
                        present = data.get("present_persons", {})
                        if present:
                            y_off = 30
                            cv2.rectangle(annotated, (5, 5), (320, 25 + len(present) * 28), (0, 0, 0), -1)
                            cv2.putText(annotated, f"Presents: {len(present)}", (10, y_off),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                            for info in present.values():
                                y_off += 28
                                dur = now - info["entry_ts"]
                                m = int(dur // 60)
                                s = int(dur % 60)
                                txt = f"  {info['prenom']} {info['nom']} - {m}:{s:02d}"
                                cv2.putText(annotated, txt, (10, y_off),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                stream["latest_frame"] = annotated

                frame_count += 1
                stream["frames_processed"] = frame_count
                stream["fps"] = frame_count / max(
                    time.time() - start_time, 0.001
                )

                # 6. Broadcast WebSocket (toutes les 5 frames)
                if frame_count % 5 == 0:
                    self._broadcast_update(camera_id)

        except Exception as e:
            logger.error(f"Erreur stream {camera_id}: {e}")
        finally:
            cap.release()
            stream["is_running"] = False
            logger.info(f"Stream {camera_id} terminé ({frame_count} frames)")

    def _broadcast_update(self, camera_id: str) -> None:
        """Envoie les mises à jour aux WebSockets connectés."""
        stream = self._streams.get(camera_id)
        if not stream:
            return

        counter = stream["counter"]
        timer = stream["timer"]

        data = {
            "type": "update",
            "camera_id": camera_id,
            "timestamp": time.time(),
            "counts": counter.get_counts(),
            "occupancy": counter.get_current_occupancy(),
            "total_entries": counter.get_total_entries(),
            "total_exits": counter.get_total_exits(),
            "active_sessions": len(timer.get_active_sessions()),
            "fps": round(stream["fps"], 1),
            "frames": stream["frames_processed"],
        }

        # Envoyer de façon asynchrone
        for ws in list(self._connected_ws):
            try:
                asyncio.run(ws.send_json(data))
            except Exception:
                self._connected_ws.remove(ws)

    def get_stats(self, camera_id: str) -> Dict:
        """Récupère les stats d'un flux."""
        stream = self._streams.get(camera_id)
        if not stream:
            return {}

        counter = stream["counter"]
        timer = stream["timer"]

        return {
            "camera_id": camera_id,
            "is_running": stream["is_running"],
            "frames_processed": stream["frames_processed"],
            "fps": round(stream["fps"], 1),
            "current_occupancy": counter.get_current_occupancy(),
            "total_entries": counter.get_total_entries(),
            "total_exits": counter.get_total_exits(),
            "total_unique_persons": stream["tracker"].get_total_unique_persons(),
            "active_persons": len(timer.get_active_sessions()),
            "counts_by_line": counter.get_counts(),
            "hourly_histogram": counter.get_hourly_histogram(),
            "presence_stats": timer.get_statistics(),
            "uptime_seconds": round(
                (datetime.now() - stream["start_time"]).total_seconds(), 1
            ),
        }

    def get_alerts(self, camera_id: str) -> List[Dict]:
        """Récupère les alertes d'un flux."""
        stream = self._streams.get(camera_id)
        if not stream:
            return []
        return stream["timer"].get_alerts()

    def get_latest_frame(self, camera_id: str) -> Optional[bytes]:
        """Retourne la dernière frame encodée en JPEG."""
        stream = self._streams.get(camera_id)
        if not stream or stream["latest_frame"] is None:
            return None
        _, buffer = cv2.imencode(".jpg", stream["latest_frame"])
        return buffer.tobytes()


# ═══════════════════════════════════════════════════════════════
# APPLICATION FASTAPI
# ═══════════════════════════════════════════════════════════════

stream_manager = StreamManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle de l'application."""
    logger.info("🚀 Surveillance-IA API démarrée")
    # Pré-initialiser InsightFace + FaceDatabase pour l'inspection
    try:
        from api.routes_persons import init_components
        init_components()
        logger.info("✅ Composants reconnaissance faciale pré-initialisés")
    except Exception as e:
        logger.warning(f"⚠️ Pré-initialisation face recog échouée: {e}")
    yield
    logger.info("⏹️ Surveillance-IA API arrêtée")
    for cam_id in list(stream_manager._streams.keys()):
        stream_manager.stop_stream(cam_id)


app = FastAPI(
    title="Surveillance-IA API",
    description=(
        "API de surveillance intelligente en temps réel.\n\n"
        "Détection YOLO v8 + ByteTrack + Comptage + Alertes.\n\n"
        "**Projet SAHELYS** — Précision ≥96%\n\n"
        "Auteur : BAWANA Théodore"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow_credentials requires explicit origin, not "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler — ensures CORS headers even on 500
from starlette.requests import Request
from starlette.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erreur interne : {exc}"},
        headers=headers,
    )

# ─── Enregistrer les routes personnes & détection ──────────
try:
    from api.routes_persons import router as persons_router
    app.include_router(persons_router)
    logger.info("✅ Routes /persons et /detect chargées")
except ImportError as e:
    logger.warning(f"⚠️ Routes personnes non disponibles : {e}")


# ─── ROUTES ─────────────────────────────────────────────────────

@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
async def login(request: TokenRequest):
    """Obtenir un token JWT."""
    token = AuthManager.authenticate(request.username, request.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
        )
    return TokenResponse(access_token=token)


@app.post("/stream/start", tags=["Stream"])
async def start_stream(
    request: StreamStartRequest,
    user: str = Depends(get_current_user),
):
    """Démarrer un flux vidéo de surveillance."""
    try:
        success = stream_manager.start_stream(
            camera_id=request.camera_id,
            source=request.source,
            model_path=request.model_path,
            conf_threshold=request.conf_threshold,
            counting_line_y=request.counting_line_y,
        )
        if success:
            return {"status": "started", "camera_id": request.camera_id}
        raise HTTPException(409, "Flux déjà actif")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur démarrage : {e}")


@app.post("/stream/stop", tags=["Stream"])
async def stop_stream(
    request: StreamStopRequest,
    user: str = Depends(get_current_user),
):
    """Arrêter un flux vidéo."""
    if stream_manager.stop_stream(request.camera_id):
        return {"status": "stopped", "camera_id": request.camera_id}
    raise HTTPException(404, "Flux non trouvé")


@app.get("/stream/status", tags=["Stream"])
async def stream_status(camera_id: str = "cam_01"):
    """Statut d'un flux."""
    stream = stream_manager._streams.get(camera_id)
    if not stream:
        return StreamStatus(camera_id=camera_id, is_running=False)

    return StreamStatus(
        camera_id=camera_id,
        is_running=stream["is_running"],
        source=stream["source"],
        frames_processed=stream["frames_processed"],
        fps=round(stream["fps"], 1),
        start_time=stream["start_time"].isoformat(),
    )


@app.get("/stats", response_model=StatsResponse, tags=["Analytics"])
async def get_stats(camera_id: str = "cam_01"):
    """Statistiques en temps réel."""
    stats = stream_manager.get_stats(camera_id)
    if not stats:
        return StatsResponse()
    return StatsResponse(**{
        k: v for k, v in stats.items()
        if k in StatsResponse.model_fields
    })


@app.get("/alerts", tags=["Analytics"])
async def get_alerts(
    camera_id: str = "cam_01",
    unacknowledged_only: bool = False,
):
    """Alertes actives."""
    alerts = stream_manager.get_alerts(camera_id)
    if unacknowledged_only:
        alerts = [a for a in alerts if not a.get("acknowledged")]
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/events", tags=["Analytics"])
async def get_events(camera_id: str = "cam_01"):
    """Historique des événements de passage."""
    stream = stream_manager._streams.get(camera_id)
    if not stream:
        return {"events": [], "count": 0}
    history = stream["counter"].get_passage_history()
    return {"events": history, "count": len(history)}


@app.get("/report/{report_date}", tags=["Reports"])
async def get_daily_report(report_date: str, camera_id: str = "cam_01"):
    """Rapport quotidien."""
    try:
        target_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Format de date invalide. Utiliser YYYY-MM-DD")

    stats = stream_manager.get_stats(camera_id)
    if not stats:
        return {
            "date": report_date,
            "camera_id": camera_id,
            "message": "Aucune donnée disponible",
        }

    return {
        "date": report_date,
        "camera_id": camera_id,
        "stats": stats,
        "alerts": stream_manager.get_alerts(camera_id),
    }


@app.get("/stream/frame", tags=["Stream"])
async def get_latest_frame(camera_id: str = "cam_01"):
    """Dernière frame annotée (JPEG)."""
    frame_bytes = stream_manager.get_latest_frame(camera_id)
    if not frame_bytes:
        raise HTTPException(404, "Aucune frame disponible")

    return StreamingResponse(
        iter([frame_bytes]),
        media_type="image/jpeg",
    )


# ─── INSPECTION (reconnaissance faciale temps réel) ─────────

@app.post("/inspection/start", tags=["Inspection"])
async def start_inspection(
    camera_id: str = "cam_01",
    user: str = Depends(get_current_user),
):
    """
    Démarre l'inspection sur un flux actif.
    Active la reconnaissance faciale en temps réel.
    Entrée = personne reconnue, Sortie = absent 20s.
    """
    if not stream_manager._streams.get(camera_id, {}).get("is_running"):
        raise HTTPException(400, "Aucun flux actif. Démarrez la caméra d'abord.")
    if stream_manager._inspection_active.get(camera_id):
        raise HTTPException(409, "Inspection déjà active")

    success = stream_manager.start_inspection(camera_id)
    if not success:
        raise HTTPException(500, "Impossible d'initialiser la reconnaissance faciale")
    return {"status": "started", "camera_id": camera_id}


@app.post("/inspection/stop", tags=["Inspection"])
async def stop_inspection(
    camera_id: str = "cam_01",
    user: str = Depends(get_current_user),
):
    """Arrête l'inspection et retourne le rapport."""
    if not stream_manager._inspection_active.get(camera_id):
        raise HTTPException(404, "Aucune inspection active")

    report = stream_manager.stop_inspection(camera_id)
    return report


@app.get("/inspection/status", tags=["Inspection"])
async def inspection_status(camera_id: str = "cam_01"):
    """Statut de l'inspection : personnes présentes, historique."""
    return stream_manager.get_inspection_status(camera_id)


@app.get("/health", tags=["System"])
async def health_check():
    """Vérification de santé."""
    return {
        "status": "healthy",
        "service": "Surveillance-IA API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "active_streams": len(stream_manager._streams),
    }


# ─── WEBSOCKET ──────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket pour les mises à jour temps réel.

    Envoie les données de détection, comptage et alertes
    en continu au client connecté.
    """
    await websocket.accept()
    stream_manager._connected_ws.append(websocket)
    logger.info("🔌 WebSocket connecté")

    try:
        while True:
            # Envoyer les stats toutes les secondes
            for camera_id, stream in stream_manager._streams.items():
                if stream["is_running"]:
                    stats = stream_manager.get_stats(camera_id)
                    await websocket.send_json({
                        "type": "stats",
                        "camera_id": camera_id,
                        "data": stats,
                        "timestamp": time.time(),
                    })

            # Écouter les messages du client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=1.0
                )
                # Traiter les commandes du client si nécessaire
                logger.info(f"WS reçu : {data}")
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket déconnecté")
    except Exception as e:
        logger.error(f"Erreur WebSocket : {e}")
    finally:
        if websocket in stream_manager._connected_ws:
            stream_manager._connected_ws.remove(websocket)


# ═══════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,
        log_level="info",
    )
