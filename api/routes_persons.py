"""
═══════════════════════════════════════════════════════════════
API Routes — Gestion des Personnes & Analyse d'Images
═══════════════════════════════════════════════════════════════
- POST /persons/register      → Enregistrer une personne (photo + infos)
- GET  /persons               → Lister les personnes
- DELETE /persons/{person_id}  → Supprimer une personne
- POST /detect/image          → Analyser une image uploadée
═══════════════════════════════════════════════════════════════
"""

import os
import time
import uuid
import logging
import base64
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

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
    init_components()

    if not _model:
        raise HTTPException(503, "Modèle YOLO non disponible")

    file_bytes = await image.read()
    img = _read_upload_as_cv2(file_bytes)

    t0 = time.time()

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
            person_crop = img[max(0, y1):y2, max(0, x1):x2]
            if person_crop.size > 0:
                faces = _face_app.get(person_crop)
                if faces and _face_db:
                    face = max(faces, key=lambda f: f.det_score)
                    embedding = face.embedding / np.linalg.norm(face.embedding)
                    identity = _face_db.identify(embedding)
                    if identity:
                        person_info["name"] = f"{identity['prenom']} {identity['nom']}"
                        person_info["similarity"] = round(identity["similarity"], 3)
                        person_info["person_id"] = identity["person_id"]

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
