"""
═══════════════════════════════════════════════════════════════
API Routes — Gestion des Personnes, Détection & Présence
═══════════════════════════════════════════════════════════════
- POST /persons/register       → Enregistrer une personne (photo + infos)
- GET  /persons                → Lister les personnes
- DELETE /persons/{person_id}  → Supprimer une personne
- POST /detect/image           → Analyser une image uploadée
- POST /detect/video           → Analyser une vidéo uploadée (présence)
- GET  /attendance/today       → Pointages du jour
- GET  /attendance/late        → Retards du jour
- GET  /attendance/absent      → Absents du jour
- GET  /attendance/stats       → Statistiques de présence
═══════════════════════════════════════════════════════════════
"""

import os
import time
import uuid
import logging
import base64
import tempfile
from typing import Optional
from collections import defaultdict

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Composants (initialisés au démarrage) ──────────────────
_model = None
_face_app = None
_face_db = None
_person_manager = None


def init_components():
    """Initialise YOLO + InsightFace + FaceDatabase au premier appel."""
    global _model, _face_app, _face_db, _person_manager

    if _model is not None:
        return

    try:
        from ultralytics import YOLO
        model_path = os.getenv("MODEL_PATH", "yolov8n.pt")
        _model = YOLO(model_path)
        logger.info(f"✅ YOLOv8 chargé : {model_path}")
    except Exception as e:
        logger.warning(f"⚠️ YOLO non disponible : {e}")

    try:
        from insightface.app import FaceAnalysis
        _face_app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        _face_app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("✅ InsightFace buffalo_l chargé")
    except TypeError:
        # Older insightface version without providers kwarg
        try:
            from insightface.app import FaceAnalysis as FA2
            _face_app = FA2(name="buffalo_l")
            _face_app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("✅ InsightFace buffalo_l chargé (legacy API)")
        except Exception as e:
            logger.warning(f"⚠️ InsightFace non disponible : {e}")
    except Exception as e:
        logger.warning(f"⚠️ InsightFace non disponible : {e}")

    try:
        from src.face_recognition import FaceDatabase
        db_path = os.getenv("FACE_DB_PATH", "data/faces.db")
        _face_db = FaceDatabase(db_path=db_path)
        logger.info(f"✅ FaceDatabase : {db_path}")
    except Exception as e:
        logger.warning(f"⚠️ FaceDatabase non disponible : {e}")


def _read_upload_as_cv2(file_bytes: bytes) -> np.ndarray:
    """Convertit des bytes uploadés en image OpenCV."""
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Impossible de décoder l'image")
    return img


def _encode_frame_base64(frame: np.ndarray, quality: int = 80) -> str:
    """Encode une frame en base64 JPEG."""
    params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    _, buffer = cv2.imencode(".jpg", frame, params)
    return base64.b64encode(buffer).decode("utf-8")


# ═══════════════════════════════════════════════════════════════
# ROUTES PERSONNES
# ═══════════════════════════════════════════════════════════════

@router.post("/persons/register", tags=["Persons"])
async def register_person(
    photo: UploadFile = File(...),
    nom: str = Form(...),
    prenom: str = Form(...),
    groupe: str = Form(""),
    role: str = Form("visiteur"),
):
    """Enregistre une nouvelle personne avec sa photo."""
    init_components()

    file_bytes = await photo.read()
    img = _read_upload_as_cv2(file_bytes)

    face_detected = False
    face_score = 0.0
    bbox = []
    embedding = None

    # Détecter les visages si InsightFace est disponible
    if _face_app:
        faces = _face_app.get(img)
        if faces:
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            embedding = face.embedding / np.linalg.norm(face.embedding)
            bbox = face.bbox.astype(int).tolist()
            face_detected = True
            face_score = float(face.det_score)

    person_id = f"P{uuid.uuid4().hex[:8].upper()}"

    # Sauvegarder dans FaceDatabase si disponible
    if _face_db:
        try:
            _face_db.add_person(
                person_id=person_id,
                nom=nom,
                prenom=prenom,
                groupe=groupe,
                role=role,
            )
            if embedding is not None:
                _face_db.add_embedding(person_id, embedding)
        except Exception as e:
            logger.error(f"Erreur FaceDatabase: {e}")
            raise HTTPException(500, f"Erreur enregistrement : {e}")
    else:
        # Fallback : JSON file
        _save_person_json(person_id, nom, prenom, groupe, role, embedding)

    return {
        "status": "registered",
        "person_id": person_id,
        "nom": nom,
        "prenom": prenom,
        "groupe": groupe,
        "role": role,
        "face_detected": face_detected,
        "face_bbox": bbox,
        "face_score": round(face_score, 3),
        "message": "Personne enregistrée" + (" avec visage" if face_detected else " sans reconnaissance faciale"),
    }


@router.get("/persons", tags=["Persons"])
async def list_persons():
    """Liste toutes les personnes enregistrées."""
    init_components()

    if _face_db:
        try:
            persons = _face_db.get_all_persons()
            result = []
            for p in persons:
                result.append({
                    "person_id": p["person_id"],
                    "nom": p["nom"],
                    "prenom": p["prenom"],
                    "groupe": p.get("groupe", ""),
                    "role": p.get("role", "visiteur"),
                    "organisation": p.get("organisation", ""),
                    "created_at": p.get("created_at", ""),
                })
            return {"persons": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(500, f"Erreur : {e}")

    # Fallback JSON
    persons = _load_persons_json()
    return {"persons": persons, "total": len(persons)}


@router.delete("/persons/{person_id}", tags=["Persons"])
async def delete_person(person_id: str):
    """Supprime une personne de la base."""
    init_components()

    if _face_db:
        try:
            _face_db.delete_person(person_id)
            return {"status": "deleted", "person_id": person_id}
        except Exception as e:
            raise HTTPException(500, f"Erreur suppression : {e}")

    raise HTTPException(404, "Personne non trouvée")


# ═══════════════════════════════════════════════════════════════
# ROUTE DÉTECTION IMAGE
# ═══════════════════════════════════════════════════════════════

@router.post("/detect/image", tags=["Detection"])
async def detect_image(
    image: UploadFile = File(...),
    conf_threshold: float = 0.3,
):
    """Analyse une image : détection de personnes + reconnaissance faciale."""
    try:
        init_components()
    except Exception as e:
        logger.warning(f"init_components error: {e}")

    if not _model:
        raise HTTPException(503, "Modèle YOLO non disponible")

    try:
        file_bytes = await image.read()
        img = _read_upload_as_cv2(file_bytes)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Erreur lecture image : {e}")

    t0 = time.time()

    try:
        # 1. Détection YOLO
        results = _model.predict(img, conf=conf_threshold, classes=[0], verbose=False)[0]
        detections = []

        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])

            person_info = {
                "bbox": [x1, y1, x2, y2],
                "confidence": round(conf, 3),
                "name": None,
                "similarity": 0.0,
            }

            # 2. Reconnaissance faciale
            if _face_app:
                try:
                    person_crop = img[max(0, y1):y2, max(0, x1):x2]
                    if person_crop.size > 0:
                        faces = _face_app.get(person_crop)
                        if faces:
                            face = max(faces, key=lambda f: f.det_score)
                            embedding = face.embedding / np.linalg.norm(face.embedding)
                            logger.info(f"  🔍 Visage détecté (score={face.det_score:.2f}), recherche dans la base...")

                            if _face_db:
                                identity = _face_db.identify(embedding, threshold=0.35)
                                if identity:
                                    person_info["name"] = f"{identity['prenom']} {identity['nom']}"
                                    person_info["similarity"] = round(identity["similarity"], 3)
                                    person_info["person_id"] = identity["person_id"]
                                    logger.info(f"  ✅ Identifié : {person_info['name']} (sim={identity['similarity']:.3f})")
                                else:
                                    logger.info(f"  ❌ Aucune correspondance trouvée (seuil=0.35)")
                            else:
                                logger.warning("  ⚠️ FaceDatabase non disponible pour l'identification")
                        else:
                            logger.info("  ℹ️ Aucun visage détecté dans le crop")
                except Exception as face_err:
                    logger.warning(f"Face recognition error: {face_err}")

            detections.append(person_info)

        elapsed_ms = (time.time() - t0) * 1000

        # 3. Annoter l'image
        annotated = img.copy()
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            name = det["name"] or "Inconnu"
            color = (0, 255, 0) if det["name"] else (0, 0, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = name
            if det["similarity"] > 0:
                label += f" ({det['similarity']:.0%})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
            cv2.putText(annotated, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        annotated_b64 = _encode_frame_base64(annotated)

        return {
            "detections": detections,
            "total_persons": len(detections),
            "total_identified": sum(1 for d in detections if d["name"]),
            "processing_ms": round(elapsed_ms, 1),
            "annotated_image": annotated_b64,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Detection error: {e}", exc_info=True)
        raise HTTPException(500, f"Erreur détection : {e}")


# ═══════════════════════════════════════════════════════════════
# FALLBACK JSON (si pas de SQLite)
# ═══════════════════════════════════════════════════════════════

_JSON_DB = "data/persons.json"


def _save_person_json(person_id, nom, prenom, groupe, role, embedding):
    import json
    os.makedirs("data", exist_ok=True)
    data = _load_persons_json()
    entry = {
        "person_id": person_id,
        "nom": nom,
        "prenom": prenom,
        "groupe": groupe,
        "role": role,
    }
    if embedding is not None:
        entry["embedding"] = embedding.tolist()
    data.append(entry)
    with open(_JSON_DB, "w") as f:
        json.dump(data, f, indent=2)


def _load_persons_json():
    import json
    if os.path.exists(_JSON_DB):
        with open(_JSON_DB) as f:
            return json.load(f)
    return []


# ═══════════════════════════════════════════════════════════════
# ROUTE DÉTECTION VIDÉO + SUIVI DE PRÉSENCE
# ═══════════════════════════════════════════════════════════════

@router.post("/detect/video", tags=["Detection"])
async def detect_video(
    video: UploadFile = File(...),
    conf_threshold: float = Form(0.3),
    frame_skip: int = Form(10),
):
    """
    Analyse une vidéo uploadée frame par frame.

    - Détecte les personnes (YOLO) et identifie les visages (InsightFace)
    - Calcule le temps de présence de chaque personne identifiée
    - Enregistre les pointages (entrée/sortie) dans la base

    Args:
        video: Fichier vidéo (mp4, avi, etc.)
        conf_threshold: Seuil de confiance YOLO (0-1)
        frame_skip: Ne traiter qu'une frame sur N (performance)

    Returns:
        Résumé avec temps de présence par personne
    """
    try:
        init_components()
    except Exception as e:
        logger.warning(f"init_components error: {e}")

    if not _model:
        raise HTTPException(503, "Modèle YOLO non disponible")

    # Sauvegarder la vidéo temporairement
    suffix = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(400, f"Erreur lecture vidéo : {e}")

    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise HTTPException(400, "Impossible d'ouvrir la vidéo")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0

        logger.info(
            f"📹 Analyse vidéo : {video.filename} | "
            f"{total_frames} frames | {fps:.1f} FPS | {duration_sec:.1f}s | "
            f"skip={frame_skip}"
        )

        t0 = time.time()

        # Tracking de présence par personne
        # person_id -> { "nom", "prenom", "first_frame", "last_frame",
        #                 "first_time_sec", "last_time_sec", "detections_count",
        #                 "similarities": [], "best_snapshot": base64 }
        presence: dict = defaultdict(lambda: {
            "nom": "", "prenom": "", "person_id": "",
            "first_frame": float("inf"), "last_frame": 0,
            "first_time_sec": 0.0, "last_time_sec": 0.0,
            "detections_count": 0, "similarities": [],
            "best_snapshot": None, "best_similarity": 0.0,
        })

        # Aussi compter les inconnus
        unknown_count = 0
        frames_processed = 0
        total_detections = 0
        annotated_keyframe = None
        keyframe_detections = 0

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip != 0:
                frame_idx += 1
                continue

            current_time_sec = frame_idx / fps if fps > 0 else 0
            frames_processed += 1

            try:
                results = _model.predict(
                    frame, conf=conf_threshold, classes=[0], verbose=False
                )[0]

                frame_det_count = 0
                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    total_detections += 1
                    frame_det_count += 1

                    identified = False

                    if _face_app:
                        try:
                            crop = frame[max(0, y1):y2, max(0, x1):x2]
                            if crop.size > 0:
                                faces = _face_app.get(crop)
                                if faces:
                                    face = max(faces, key=lambda f: f.det_score)
                                    emb = face.embedding / np.linalg.norm(face.embedding)

                                    if _face_db:
                                        identity = _face_db.identify(emb, threshold=0.35)
                                        if identity:
                                            pid = identity["person_id"]
                                            p = presence[pid]
                                            p["person_id"] = pid
                                            p["nom"] = identity["nom"]
                                            p["prenom"] = identity["prenom"]
                                            p["first_frame"] = min(p["first_frame"], frame_idx)
                                            p["last_frame"] = max(p["last_frame"], frame_idx)
                                            p["first_time_sec"] = p["first_frame"] / fps if fps > 0 else 0
                                            p["last_time_sec"] = p["last_frame"] / fps if fps > 0 else 0
                                            p["detections_count"] += 1
                                            p["similarities"].append(identity["similarity"])

                                            # Garder le meilleur snapshot
                                            if identity["similarity"] > p["best_similarity"]:
                                                p["best_similarity"] = identity["similarity"]
                                                face_crop = frame[max(0, y1-20):min(frame.shape[0], y2+20),
                                                                   max(0, x1-20):min(frame.shape[1], x2+20)]
                                                if face_crop.size > 0:
                                                    p["best_snapshot"] = _encode_frame_base64(face_crop)

                                            identified = True
                        except Exception as face_err:
                            logger.debug(f"Face error frame {frame_idx}: {face_err}")

                    if not identified:
                        unknown_count += 1

                # Garder la frame avec le plus de détections comme keyframe
                if frame_det_count > keyframe_detections:
                    keyframe_detections = frame_det_count
                    # Annoter la keyframe
                    annotated = frame.copy()
                    for box in results.boxes:
                        bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
                    annotated_keyframe = _encode_frame_base64(annotated)

            except Exception as e:
                logger.debug(f"Frame {frame_idx} error: {e}")

            frame_idx += 1

        cap.release()
        elapsed_ms = (time.time() - t0) * 1000

        # Construire le résumé de présence
        presence_summary = []
        for pid, p in presence.items():
            if p["detections_count"] == 0:
                continue

            duration = p["last_time_sec"] - p["first_time_sec"]
            avg_sim = sum(p["similarities"]) / len(p["similarities"]) if p["similarities"] else 0

            presence_summary.append({
                "person_id": pid,
                "nom": p["nom"],
                "prenom": p["prenom"],
                "name": f"{p['prenom']} {p['nom']}",
                "first_seen_sec": round(p["first_time_sec"], 1),
                "last_seen_sec": round(p["last_time_sec"], 1),
                "duration_sec": round(duration, 1),
                "duration_formatted": _format_duration(duration),
                "detections_count": p["detections_count"],
                "avg_similarity": round(avg_sim, 3),
                "best_similarity": round(p["best_similarity"], 3),
                "snapshot": p["best_snapshot"],
            })

            # Enregistrer le pointage dans la base
            if _face_db:
                try:
                    _face_db.record_attendance(
                        person_id=pid,
                        direction="entry",
                        similarity=avg_sim,
                        camera_id="video_upload",
                    )
                    if duration > 0:
                        _face_db.record_attendance(
                            person_id=pid,
                            direction="exit",
                            similarity=avg_sim,
                            camera_id="video_upload",
                        )
                except Exception as att_err:
                    logger.warning(f"Attendance record error for {pid}: {att_err}")

        # Trier par durée décroissante
        presence_summary.sort(key=lambda x: x["duration_sec"], reverse=True)

        logger.info(
            f"✅ Vidéo traitée : {frames_processed} frames | "
            f"{len(presence_summary)} personnes identifiées | "
            f"{unknown_count} détections inconnues | {elapsed_ms:.0f}ms"
        )

        return {
            "video_info": {
                "filename": video.filename,
                "fps": round(fps, 1),
                "total_frames": total_frames,
                "duration_sec": round(duration_sec, 1),
                "duration_formatted": _format_duration(duration_sec),
                "frames_processed": frames_processed,
                "frame_skip": frame_skip,
            },
            "presence": presence_summary,
            "total_persons_identified": len(presence_summary),
            "total_detections": total_detections,
            "unknown_detections": unknown_count,
            "processing_ms": round(elapsed_ms, 1),
            "annotated_keyframe": annotated_keyframe,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video detection error: {e}", exc_info=True)
        raise HTTPException(500, f"Erreur analyse vidéo : {e}")
    finally:
        # Nettoyer le fichier temporaire
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _format_duration(seconds: float) -> str:
    """Formate une durée en secondes en HH:MM:SS lisible."""
    if seconds <= 0:
        return "0s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}min")
    if s > 0 or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════
# ROUTES PRÉSENCE / POINTAGE
# ═══════════════════════════════════════════════════════════════

@router.get("/attendance/today", tags=["Attendance"])
async def attendance_today(
    person_id: Optional[str] = Query(None, description="Filtrer par personne"),
):
    """Retourne les pointages du jour (tous ou pour une personne)."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        records = _face_db.get_attendance_today(person_id=person_id)
        return {"records": records, "total": len(records), "date": time.strftime("%Y-%m-%d")}
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@router.get("/attendance/late", tags=["Attendance"])
async def attendance_late():
    """Retourne les retards du jour."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        records = _face_db.get_late_today()
        return {"records": records, "total": len(records), "date": time.strftime("%Y-%m-%d")}
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@router.get("/attendance/absent", tags=["Attendance"])
async def attendance_absent():
    """Retourne les personnes absentes aujourd'hui."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        records = _face_db.get_absent_today()
        return {"records": records, "total": len(records), "date": time.strftime("%Y-%m-%d")}
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@router.get("/attendance/presence", tags=["Attendance"])
async def attendance_presence(
    person_id: Optional[str] = Query(None, description="Filtrer par personne"),
):
    """Durée de présence par personne aujourd'hui (entrée → sortie)."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        records = _face_db.get_presence_duration_today(person_id=person_id)
        total_duration = sum(r["duration_sec"] for r in records)
        return {
            "records": records,
            "total": len(records),
            "total_duration_sec": round(total_duration, 1),
            "date": time.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@router.get("/attendance/stats", tags=["Attendance"])
async def attendance_stats(
    date_from: Optional[str] = Query(None, description="Date début YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Date fin YYYY-MM-DD"),
):
    """Statistiques de présence sur une période."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        stats = _face_db.get_attendance_stats(
            date_from=date_from, date_to=date_to
        )
        return stats
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@router.get("/attendance/history/{person_id}", tags=["Attendance"])
async def attendance_history(
    person_id: str,
    date_from: Optional[str] = Query(None, description="Date début YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Date fin YYYY-MM-DD"),
):
    """Historique détaillé par personne avec données jour par jour (pour graphiques)."""
    init_components()
    if not _face_db:
        raise HTTPException(503, "Base de données non disponible")

    try:
        history = _face_db.get_person_attendance_history(
            person_id=person_id, date_from=date_from, date_to=date_to
        )
        return history
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


# ─── Settings ──────────────────────────────────────────────────
_SETTINGS_PATH = os.path.join("data", "settings.json")


def _load_settings() -> dict:
    """Charge les paramètres depuis le fichier JSON."""
    defaults = {
        "recording_periods": [],
        "absence_timeout_sec": 20,
        "face_recognition_threshold": 0.4,
        "face_recognition_interval": 5,
        "late_threshold_minutes": 15,
        "camera_source": "0",
        "auto_start_inspection": False,
        "notification_enabled": False,
        "export_format": "csv",
    }
    try:
        if os.path.exists(_SETTINGS_PATH):
            import json as _json
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = _json.load(f)
                defaults.update(saved)
    except Exception:
        pass
    return defaults


def _save_settings(settings: dict):
    """Sauvegarde les paramètres dans le fichier JSON."""
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    import json as _json
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        _json.dump(settings, f, indent=2, ensure_ascii=False)


@router.get("/settings", tags=["Settings"])
async def get_settings():
    """Récupère les paramètres de configuration."""
    return _load_settings()


@router.put("/settings", tags=["Settings"])
async def update_settings(body: dict):
    """Met à jour les paramètres de configuration."""
    current = _load_settings()
    current.update(body)
    _save_settings(current)
    return {"status": "updated", "settings": current}
