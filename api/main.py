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
            logger.warning(f"Flux déjà actif : {camera_id}")
            return False

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

        logger.info(f"✅ Flux démarré : {camera_id} → {source}")
        return True

    def stop_stream(self, camera_id: str) -> bool:
        """Arrête un flux de surveillance."""
        if camera_id not in self._streams:
            return False

        self._stop_events[camera_id].set()
        self._streams[camera_id]["is_running"] = False

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
                    stream["latest_frame"] = annotated

                frame_count += 1
                stream["frames_processed"] = frame_count
                stream["fps"] = frame_count / max(
                    time.time() - start_time, 0.001
                )

                # 5. Broadcast WebSocket (toutes les 5 frames)
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
