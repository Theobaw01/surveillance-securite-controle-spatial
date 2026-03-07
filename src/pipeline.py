"""
═══════════════════════════════════════════════════════════════
MODULE 8 — Pipeline Surveillance Temps Réel
═══════════════════════════════════════════════════════════════
Assemble : Tracker + Counter + Timer + Face Recognition

Fonctionnalités :
- Détection + Tracking (YOLO v8 + ByteTrack)
- Reconnaissance faciale (InsightFace Buffalo)
- Identification par nom/prénom (base de visages)
- Comptage entrées/sorties (lignes virtuelles)
- Chronomètre de présence par personne
- Suivi des retards (configurable par profil : entreprise, école, événement...)
- Overlay temps réel avec identités
- Export CSV / JSON des événements
═══════════════════════════════════════════════════════════════
"""

import os
import csv
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import cv2
import numpy as np

from src.tracker import PersonTracker, TrackingFrame
from src.counter import PersonCounter, VirtualLine, Direction, PassageEvent
from src.timer import PresenceTimer, TimerAlert

# Face recognition (optionnel — désactivé si insightface absent)
try:
    from src.face_recognition import FaceRecognizer, FaceDatabase, IdentifiedPerson
    from src.person_manager import PersonManager, StudentManager
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SurveillancePipeline:
    """
    Pipeline complet de surveillance temps réel.

    Combine :
    - PersonTracker  → détection + suivi YOLO v8 + ByteTrack
    - PersonCounter  → comptage IN/OUT via lignes virtuelles
    - PresenceTimer  → chronomètre de présence par personne

    Produit :
    - Nombre d'entrées et sorties
    - Heure d'entrée et de sortie de chaque personne
    - Durée de présence
    - Occupation en temps réel
    - Alertes (seuils de temps)
    """

    def __init__(
        self,
        model_path: str,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.5,
        absence_timeout: float = 10.0,
        alert_thresholds: Optional[List[float]] = None,
        output_dir: str = "outputs",
        # Face recognition
        enable_face_recognition: bool = False,
        face_db_path: str = "data/faces.db",
        face_model: str = "buffalo_l",
        face_threshold: float = 0.45,
        profil: str = "libre",
        organisation: str = "",
    ):
        """
        Args:
            model_path: Chemin vers le modèle YOLO fine-tuné (best.pt).
            conf_threshold: Seuil de confiance YOLO.
            iou_threshold: Seuil IoU pour NMS.
            absence_timeout: Temps (s) avant de considérer une personne sortie.
            alert_thresholds: Seuils d'alerte de présence (secondes).
            output_dir: Dossier de sortie pour les rapports.
            enable_face_recognition: Activer la reconnaissance faciale.
            face_db_path: Chemin vers la base SQLite des visages.
            face_model: Modèle InsightFace (buffalo_l, buffalo_s).
            face_threshold: Seuil de similarité (0.4-0.6).
            profil: Profil de gestion (ecole, entreprise, evenement...).
            organisation: Nom de l'organisation.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ── Initialiser les composants ──
        self.tracker = PersonTracker(
            model_path=model_path,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )

        self.counter = PersonCounter()

        self.timer = PresenceTimer(
            absence_timeout=absence_timeout,
            alert_thresholds=alert_thresholds or [60, 300, 600],
            on_alert=self._on_alert,
        )

        # ── Reconnaissance faciale (optionnel) ──
        self.face_recognition_enabled = False
        self.face_recognizer: Optional[FaceRecognizer] = None
        self.face_db: Optional[FaceDatabase] = None
        self.person_manager: Optional[PersonManager] = None
        self._track_to_identity: Dict[int, IdentifiedPerson] = {}
        self._face_check_interval = 10  # vérifier tous les N frames
        self._last_face_check: Dict[int, int] = {}  # track_id → dernier frame vérifié

        if enable_face_recognition and FACE_RECOGNITION_AVAILABLE:
            try:
                self.face_db = FaceDatabase(db_path=face_db_path)
                self.face_recognizer = FaceRecognizer(
                    face_db=self.face_db,
                    model_name=face_model,
                    similarity_threshold=face_threshold,
                )
                self.person_manager = PersonManager(
                    face_db=self.face_db,
                    profil=profil,
                    organisation=organisation,
                )
                self.face_recognition_enabled = True
                logger.info(
                    f"   🔍 Reconnaissance faciale ACTIVE | "
                    f"Seuil: {face_threshold} | "
                    f"Personnes: {len(self.face_db.get_all_persons())}"
                )
            except Exception as e:
                logger.warning(f"   ⚠️ Reconnaissance faciale désactivée : {e}")
        elif enable_face_recognition and not FACE_RECOGNITION_AVAILABLE:
            logger.warning(
                "   ⚠️ insightface non installé → reconnaissance faciale désactivée\n"
                "   Installer : pip install insightface onnxruntime-gpu"
            )

        # ── État ──
        self._start_time = None
        self._frame_count = 0
        self._events_log: List[Dict] = []
        self._alerts_log: List[Dict] = []

        logger.info(
            f"✅ SurveillancePipeline initialisé\n"
            f"   Modèle      : {model_path}\n"
            f"   Confiance    : {conf_threshold}\n"
            f"   Timeout      : {absence_timeout}s\n"
            f"   Seuils alerte: {alert_thresholds or [60, 300, 600]}s\n"
            f"   Reconnaissance: {'✅ Active' if self.face_recognition_enabled else '❌ Désactivée'}"
        )

    def setup_counting_line(
        self,
        name: str = "Entrée Principale",
        position: str = "middle",
        orientation: str = "horizontal",
        entry_direction: str = "down",
        frame_width: int = 1920,
        frame_height: int = 1080,
        y_ratio: float = 0.5,
        x_ratio: float = 0.5,
    ) -> None:
        """
        Configure une ligne virtuelle de comptage.

        Args:
            name: Nom de la ligne.
            position: "middle", "top_third", "bottom_third", "custom".
            orientation: "horizontal" ou "vertical".
            entry_direction: "down", "up", "left", "right".
            frame_width: Largeur de la frame.
            frame_height: Hauteur de la frame.
            y_ratio: Position Y en ratio (0-1) pour horizontal.
            x_ratio: Position X en ratio (0-1) pour vertical.
        """
        if orientation == "horizontal":
            if position == "middle":
                y = frame_height // 2
            elif position == "top_third":
                y = frame_height // 3
            elif position == "bottom_third":
                y = 2 * frame_height // 3
            else:
                y = int(frame_height * y_ratio)

            self.counter.add_horizontal_line(
                name=name, y=y,
                x_start=0, x_end=frame_width,
                entry_direction=entry_direction,
            )
        else:
            if position == "middle":
                x = frame_width // 2
            elif position == "left_third":
                x = frame_width // 3
            elif position == "right_third":
                x = 2 * frame_width // 3
            else:
                x = int(frame_width * x_ratio)

            self.counter.add_vertical_line(
                name=name, x=x,
                y_start=0, y_end=frame_height,
                entry_direction=entry_direction,
            )

    def _on_alert(self, alert: TimerAlert) -> None:
        """Callback quand une alerte de présence est déclenchée."""
        self._alerts_log.append({
            "person_id": alert.person_id,
            "type": alert.alert_type,
            "threshold_s": alert.threshold_seconds,
            "actual_s": round(alert.actual_seconds, 1),
            "message": alert.message,
            "datetime": datetime.fromtimestamp(alert.timestamp).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        })

    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Traite une frame complète : détection → tracking → comptage → timer.

        Args:
            frame: Image BGR (OpenCV).

        Returns:
            Dictionnaire avec toutes les infos de la frame.
        """
        if self._start_time is None:
            self._start_time = time.time()

        self._frame_count += 1

        # 1. TRACKING : détection + suivi
        tracking_result = self.tracker.track_frame(frame, draw=True)

        # 2. RECONNAISSANCE FACIALE : identifier les personnes par visage
        identifications: Dict[int, IdentifiedPerson] = {}
        if self.face_recognition_enabled and self.face_recognizer:
            identifications = self._identify_tracked_persons(
                frame, tracking_result
            )

        # 3. COMPTAGE : vérifier les croisements de lignes
        new_passages = self.counter.update(tracking_result)

        # 4. TIMER : mettre à jour les chronomètres
        active_ids = [p.track_id for p in tracking_result.persons if p.track_id >= 0]
        new_alerts = self.timer.update(active_ids)

        # 5. Pointage automatique : enregistrer les passages identifiés
        if self.face_recognition_enabled and self.face_db:
            for event in new_passages:
                identity = identifications.get(event.track_id)
                if identity:
                    direction = "entry" if event.direction == Direction.ENTRY else "exit"
                    self.face_db.record_attendance(
                        person_id=identity.person_id,
                        direction=direction,
                        similarity=identity.similarity,
                    )

        # Logger les passages
        for event in new_passages:
            identity = identifications.get(event.track_id)
            passage_log = {
                "type": "passage",
                "person_id": event.track_id,
                "direction": event.direction.value,
                "line": event.line_name,
                "datetime": event.datetime_str,
                "confidence": round(event.confidence, 3),
            }
            if identity:
                passage_log["identity"] = identity.full_name
                passage_log["identity_id"] = identity.person_id
                passage_log["similarity"] = round(identity.similarity, 3)
            self._events_log.append(passage_log)

        # Construire l'overlay combiné
        display_frame = tracking_result.annotated_frame
        if display_frame is not None:
            display_frame = self.counter.draw_overlay(display_frame)
            display_frame = self._draw_timer_overlay(display_frame)
            display_frame = self._draw_identities_overlay(display_frame, tracking_result, identifications)
            display_frame = self._draw_stats_overlay(display_frame, tracking_result)

        # Résultat complet
        counts = self.counter.get_counts()
        active_sessions = self.timer.get_active_sessions()

        return {
            "frame_id": self._frame_count,
            "timestamp": time.time(),
            "persons_detected": tracking_result.total_detected,
            "total_unique": self.tracker.get_total_unique_persons(),
            "fps": tracking_result.fps,
            "counts": counts,
            "total_entries": self.counter.get_total_entries(),
            "total_exits": self.counter.get_total_exits(),
            "occupancy": self.counter.get_current_occupancy(),
            "active_sessions": active_sessions,
            "new_passages": [
                {
                    "person_id": e.track_id,
                    "direction": e.direction.value,
                    "time": e.datetime_str,
                }
                for e in new_passages
            ],
            "new_alerts": [
                {"person_id": a.person_id, "message": a.message}
                for a in new_alerts
            ],
            "display_frame": display_frame,
        }

    # ─── Reconnaissance faciale ─────────────────────────────────

    def _identify_tracked_persons(
        self,
        frame: np.ndarray,
        tracking: TrackingFrame,
    ) -> Dict[int, IdentifiedPerson]:
        """
        Identifie les personnes trackées par reconnaissance faciale.

        Ne vérifie pas chaque frame pour chaque personne (performance).
        Utilise un cache : une fois identifié, le track_id garde l'identité.
        """
        identifications = dict(self._track_to_identity)

        for person in tracking.persons:
            tid = person.track_id
            if tid < 0:
                continue

            # Déjà identifié → garder l'identité
            if tid in identifications:
                continue

            # Vérifier seulement tous les N frames par personne
            last_check = self._last_face_check.get(tid, 0)
            if self._frame_count - last_check < self._face_check_interval:
                continue
            self._last_face_check[tid] = self._frame_count

            # Extraire le crop de la personne
            x1, y1, x2, y2 = person.bbox
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 - x1 < 40 or y2 - y1 < 40:
                continue

            crop = frame[y1:y2, x1:x2]

            try:
                faces = self.face_recognizer.detect_faces(crop)
                if faces:
                    # Prendre le visage le plus grand
                    face = max(
                        faces,
                        key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]),
                    )
                    identity = self.face_recognizer.identify(face)
                    if identity:
                        # Ajuster la bbox du visage dans le repère global
                        fx1, fy1, fx2, fy2 = face.bbox
                        identity.face_bbox = (
                            x1 + fx1, y1 + fy1,
                            x1 + fx2, y1 + fy2,
                        )
                        identifications[tid] = identity
                        self._track_to_identity[tid] = identity
                        logger.info(
                            f"  🔍 ID:{tid} → {identity.full_name} "
                            f"(sim: {identity.similarity:.1%})"
                        )
            except Exception as e:
                logger.debug(f"  Face detect error on track {tid}: {e}")

        # Nettoyer les identités de tracks disparus
        active_ids = {p.track_id for p in tracking.persons}
        for tid in list(self._track_to_identity.keys()):
            if tid not in active_ids:
                del self._track_to_identity[tid]
                self._last_face_check.pop(tid, None)

        return identifications

    def _draw_identities_overlay(
        self,
        frame: np.ndarray,
        tracking: TrackingFrame,
        identifications: Dict[int, IdentifiedPerson],
    ) -> np.ndarray:
        """Dessine les noms des personnes identifiées sur la frame."""
        if not identifications:
            return frame

        annotated = frame.copy()

        for person in tracking.persons:
            tid = person.track_id
            identity = identifications.get(tid)
            if not identity:
                continue

            x1, y1, x2, y2 = person.bbox

            # Label avec nom et info
            label = identity.display_label
            sim_label = f"{identity.similarity:.0%}"

            # Background du label principal (vert)
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2,
            )
            lbl_y = max(y1 - th - 25, th + 5)

            cv2.rectangle(
                annotated,
                (x1, lbl_y - th - 5),
                (x1 + tw + 8, lbl_y + 5),
                (0, 180, 0), -1,
            )
            cv2.putText(
                annotated, label,
                (x1 + 4, lbl_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2,
            )

            # Petit label de similarité sous le nom
            cv2.putText(
                annotated, sim_label,
                (x1 + 4, lbl_y + th + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                (0, 255, 0), 1,
            )

            # Cadre vert autour du visage (si bbox dispos)
            if identity.face_bbox != (0, 0, 0, 0):
                fx1, fy1, fx2, fy2 = identity.face_bbox
                cv2.rectangle(annotated, (fx1, fy1), (fx2, fy2), (0, 255, 0), 2)

        # Panel des identités (côté gauche)
        if identifications:
            panel_w = 280
            panel_h = 30 + len(identifications) * 22
            y_start = 55

            cv2.rectangle(
                annotated,
                (10, y_start),
                (10 + panel_w, y_start + panel_h),
                (0, 0, 0), -1,
            )
            cv2.putText(
                annotated, "IDENTITES",
                (20, y_start + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 255, 0), 2,
            )

            y = y_start + 42
            for tid, identity in identifications.items():
                txt = f"#{tid} {identity.full_name} ({identity.similarity:.0%})"
                cv2.putText(
                    annotated, txt,
                    (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255, 255, 255), 1,
                )
                y += 22

        return annotated

    def _draw_timer_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Dessine les chronomètres de présence sur la frame."""
        active = self.timer.get_active_sessions()
        if not active:
            return frame

        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Panneau des timers en haut à droite
        panel_w = 280
        panel_h = 30 + len(active) * 25
        x_start = w - panel_w - 10
        y_start = 10

        cv2.rectangle(
            annotated,
            (x_start, y_start),
            (w - 10, y_start + panel_h),
            (0, 0, 0), -1,
        )

        cv2.putText(
            annotated, "PRESENCE",
            (x_start + 10, y_start + 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            (255, 255, 0), 2,
        )

        y = y_start + 45
        for tid, session in active.items():
            elapsed = session.get("elapsed", 0)
            elapsed_str = session.get("elapsed_str", "0:00:00")

            # Couleur selon la durée
            if elapsed > 600:
                color = (0, 0, 255)    # Rouge > 10 min
            elif elapsed > 300:
                color = (0, 165, 255)  # Orange > 5 min
            elif elapsed > 60:
                color = (0, 255, 255)  # Jaune > 1 min
            else:
                color = (0, 255, 0)    # Vert < 1 min

            text = f"ID:{tid} | {elapsed_str}"
            cv2.putText(
                annotated, text,
                (x_start + 10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                color, 1,
            )
            y += 25

        return annotated

    def _draw_stats_overlay(
        self, frame: np.ndarray, tracking: TrackingFrame
    ) -> np.ndarray:
        """Dessine les statistiques globales en haut de la frame."""
        annotated = frame.copy()
        elapsed = time.time() - (self._start_time or time.time())

        entries = self.counter.get_total_entries()
        exits = self.counter.get_total_exits()
        occupancy = self.counter.get_current_occupancy()

        # Barre de stats en haut
        bar_h = 40
        cv2.rectangle(annotated, (0, 0), (annotated.shape[1], bar_h), (50, 50, 50), -1)

        stats_text = (
            f"Personnes: {tracking.total_detected} | "
            f"IN: {entries} | OUT: {exits} | "
            f"Occupation: {occupancy} | "
            f"IDs uniques: {self.tracker.get_total_unique_persons()} | "
            f"FPS: {tracking.fps:.1f} | "
            f"Temps: {timedelta(seconds=int(elapsed))}"
        )

        cv2.putText(
            annotated, stats_text,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
            (0, 255, 0), 1,
        )

        return annotated

    def run(
        self,
        source: str,
        output_video: Optional[str] = None,
        show: bool = True,
        max_frames: Optional[int] = None,
        auto_line: bool = True,
    ) -> Dict:
        """
        Lance le pipeline complet sur une source vidéo.

        Args:
            source: Chemin vidéo, URL RTSP, ou "0" pour webcam.
            output_video: Sauvegarde de la vidéo annotée.
            show: Afficher en temps réel.
            max_frames: Limite de frames.
            auto_line: Configurer une ligne automatiquement au milieu.

        Returns:
            Rapport complet de la session.
        """
        # Ouvrir la source
        src = int(source) if source.isdigit() else source
        cap = cv2.VideoCapture(src)

        if not cap.isOpened():
            raise ValueError(f"Impossible d'ouvrir la source : {source}")

        # Propriétés vidéo
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logger.info(
            f"📹 Source: {source} | {width}x{height} | "
            f"{fps:.1f} FPS | {total_frames} frames"
        )

        # Ligne virtuelle automatique au milieu
        if auto_line and len(self.counter.lines) == 0:
            self.setup_counting_line(
                name="Ligne Principale",
                position="middle",
                orientation="horizontal",
                entry_direction="down",
                frame_width=width,
                frame_height=height,
            )

        # Writer vidéo de sortie
        writer = None
        if output_video:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_video, fourcc, fps, (width, height))

        # Reset
        self._start_time = time.time()
        self._frame_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if max_frames and self._frame_count >= max_frames:
                    break

                # Traiter la frame
                result = self.process_frame(frame)

                # Écrire la vidéo
                if writer and result["display_frame"] is not None:
                    writer.write(result["display_frame"])

                # Afficher
                if show and result["display_frame"] is not None:
                    cv2.imshow("Surveillance-IA", result["display_frame"])
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        logger.info("⏹️ Arrêt demandé par l'utilisateur")
                        break
                    elif key == ord("r"):
                        self.counter.reset()
                        self.timer.reset()
                        logger.info("🔄 Compteurs réinitialisés")
                    elif key == ord("s"):
                        self._save_snapshot(result["display_frame"])

                # Log périodique
                if self._frame_count % 200 == 0:
                    logger.info(
                        f"  Frame {self._frame_count}/{total_frames} | "
                        f"IN={result['total_entries']} OUT={result['total_exits']} "
                        f"Occup={result['occupancy']} | "
                        f"FPS={result['fps']:.1f}"
                    )

        finally:
            cap.release()
            if writer:
                writer.release()
            if show:
                cv2.destroyAllWindows()

        # Forcer la fermeture des sessions actives
        self.timer.update([])  # Pas de personnes → ferme tout après timeout

        # Générer le rapport
        report = self._generate_report(source, total_frames)
        return report

    def _save_snapshot(self, frame: np.ndarray) -> None:
        """Sauvegarde un snapshot."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"snapshot_{ts}.jpg"
        cv2.imwrite(str(path), frame)
        logger.info(f"📸 Snapshot : {path}")

    def _generate_report(self, source: str, total_frames: int) -> Dict:
        """Génère le rapport complet de la session."""
        elapsed = time.time() - (self._start_time or time.time())

        # Sessions du timer
        all_sessions = self.timer.get_all_sessions()
        completed = self.timer.get_completed_sessions()
        stats = self.timer.get_statistics()

        # Comptages
        counts = self.counter.get_counts()
        history = self.counter.get_passage_history()
        histogram = self.counter.get_hourly_histogram()

        report = {
            "session": {
                "source": source,
                "start_time": datetime.fromtimestamp(
                    self._start_time
                ).strftime("%Y-%m-%d %H:%M:%S") if self._start_time else "",
                "duration_seconds": round(elapsed, 1),
                "duration_str": str(timedelta(seconds=int(elapsed))),
                "total_frames": self._frame_count,
                "total_video_frames": total_frames,
            },
            "counting": {
                "total_entries": self.counter.get_total_entries(),
                "total_exits": self.counter.get_total_exits(),
                "final_occupancy": self.counter.get_current_occupancy(),
                "total_unique_persons": self.tracker.get_total_unique_persons(),
                "by_line": counts,
                "hourly_histogram": histogram,
            },
            "presence": {
                "total_sessions": stats.get("total_sessions", 0),
                "avg_duration_s": stats.get("avg_duration", 0),
                "avg_duration_str": stats.get("avg_duration_str", "0:00:00"),
                "min_duration_s": stats.get("min_duration", 0),
                "max_duration_s": stats.get("max_duration", 0),
                "median_duration_s": stats.get("median_duration", 0),
                "sessions": all_sessions,
            },
            "alerts": {
                "total": len(self._alerts_log),
                "details": self._alerts_log,
            },
            "events": self._events_log,
            "passage_history": history,
        }

        # Sauvegarder le rapport
        self._save_report(report)

        return report

    def _save_report(self, report: Dict) -> None:
        """Sauvegarde le rapport en JSON et CSV."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON complet
        json_path = self.output_dir / f"rapport_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"📄 Rapport JSON : {json_path}")

        # CSV des passages
        csv_path = self.output_dir / f"passages_{ts}.csv"
        passages = report.get("passage_history", [])
        if passages:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "datetime", "track_id", "direction",
                        "line", "confidence",
                    ],
                )
                writer.writeheader()
                for p in passages:
                    writer.writerow({
                        "datetime": p.get("datetime", ""),
                        "track_id": p.get("track_id", ""),
                        "direction": p.get("direction", ""),
                        "line": p.get("line", ""),
                        "confidence": p.get("confidence", ""),
                    })
            logger.info(f"📊 Passages CSV : {csv_path}")

        # CSV des sessions de présence
        sessions_csv = self.output_dir / f"presence_{ts}.csv"
        sessions = report.get("presence", {}).get("sessions", [])
        if sessions:
            with open(sessions_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "person_id", "entry_datetime", "exit_datetime",
                        "duration", "elapsed_str",
                    ],
                )
                writer.writeheader()
                for s in sessions:
                    writer.writerow({
                        "person_id": s.get("person_id", ""),
                        "entry_datetime": s.get("entry_datetime", ""),
                        "exit_datetime": s.get("exit_datetime", ""),
                        "duration": round(s.get("duration", 0) or 0, 1),
                        "elapsed_str": s.get("elapsed_str", ""),
                    })
            logger.info(f"⏱️ Présence CSV : {sessions_csv}")

    def print_summary(self, report: Dict) -> None:
        """Affiche un résumé lisible du rapport."""
        session = report["session"]
        counting = report["counting"]
        presence = report["presence"]
        alerts = report["alerts"]

        print(f"\n{'='*60}")
        print(f"  {'RAPPORT DE SURVEILLANCE — Surveillance-IA':^56}")
        print(f"{'='*60}")
        print(f"  Source        : {session['source']}")
        print(f"  Début         : {session['start_time']}")
        print(f"  Durée         : {session['duration_str']}")
        print(f"  Frames        : {session['total_frames']}")
        print(f"{'─'*60}")
        print(f"  {'COMPTAGE':^56}")
        print(f"{'─'*60}")
        print(f"  Entrées       : {counting['total_entries']}")
        print(f"  Sorties       : {counting['total_exits']}")
        print(f"  Occupation    : {counting['final_occupancy']}")
        print(f"  IDs uniques   : {counting['total_unique_persons']}")

        if counting["by_line"]:
            print(f"\n  Par ligne :")
            for name, data in counting["by_line"].items():
                print(
                    f"    {name}: IN={data['entries']} "
                    f"OUT={data['exits']} [{data['occupancy']}]"
                )

        print(f"{'─'*60}")
        print(f"  {'PRÉSENCE':^56}")
        print(f"{'─'*60}")
        print(f"  Sessions      : {presence['total_sessions']}")
        print(f"  Durée moyenne : {presence['avg_duration_str']}")
        print(f"  Durée min     : {timedelta(seconds=int(presence['min_duration_s']))}")
        print(f"  Durée max     : {timedelta(seconds=int(presence['max_duration_s']))}")

        if alerts["total"] > 0:
            print(f"{'─'*60}")
            print(f"  ⚠️ ALERTES : {alerts['total']}")
            for a in alerts["details"][:5]:
                print(f"    • {a['datetime']} — {a['message']}")

        print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Surveillance-IA — Pipeline complet de surveillance temps réel",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--model", required=True,
        help="Chemin vers le modèle YOLO (ex: models/finetuned/best.pt)",
    )
    parser.add_argument(
        "--source", default="0",
        help="Source vidéo :\n"
             "  '0'           → webcam\n"
             "  'video.mp4'   → fichier vidéo\n"
             "  'rtsp://...'  → flux RTSP",
    )
    parser.add_argument("--output", default=None, help="Chemin vidéo annotée de sortie")
    parser.add_argument("--output-dir", default="outputs", help="Dossier des rapports")
    parser.add_argument("--conf", type=float, default=0.35, help="Seuil de confiance")
    parser.add_argument("--iou", type=float, default=0.5, help="Seuil IoU NMS")
    parser.add_argument("--show", action="store_true", help="Afficher la vidéo temps réel")
    parser.add_argument("--no-show", action="store_true", help="Désactiver l'affichage")
    parser.add_argument("--max-frames", type=int, default=None, help="Limite de frames")
    parser.add_argument(
        "--timeout", type=float, default=10.0,
        help="Temps (s) avant de considérer une personne sortie",
    )
    parser.add_argument(
        "--alerts", nargs="*", type=float, default=[60, 300, 600],
        help="Seuils d'alerte de présence en secondes (défaut: 60 300 600)",
    )
    parser.add_argument(
        "--line-position", default="middle",
        choices=["middle", "top_third", "bottom_third"],
        help="Position de la ligne de comptage",
    )
    parser.add_argument(
        "--line-direction", default="down",
        choices=["down", "up", "left", "right"],
        help="Direction considérée comme 'entrée'",
    )
    parser.add_argument(
        "--line-orientation", default="horizontal",
        choices=["horizontal", "vertical"],
        help="Orientation de la ligne de comptage",
    )

    # Face recognition
    parser.add_argument(
        "--face", action="store_true",
        help="Activer la reconnaissance faciale",
    )
    parser.add_argument(
        "--face-db", default="data/faces.db",
        help="Chemin vers la base SQLite des visages",
    )
    parser.add_argument(
        "--face-model", default="buffalo_l",
        choices=["buffalo_l", "buffalo_s", "buffalo_sc"],
        help="Modèle InsightFace",
    )
    parser.add_argument(
        "--face-threshold", type=float, default=0.45,
        help="Seuil de similarité faciale (défaut: 0.45)",
    )
    parser.add_argument(
        "--profil", default="libre",
        choices=["ecole", "entreprise", "evenement", "batiment", "libre"],
        help="Profil de gestion des personnes",
    )
    parser.add_argument(
        "--organisation", default="",
        help="Nom de l'organisation",
    )

    args = parser.parse_args()

    # Créer le pipeline
    pipeline = SurveillancePipeline(
        model_path=args.model,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        absence_timeout=args.timeout,
        alert_thresholds=args.alerts,
        output_dir=args.output_dir,
        enable_face_recognition=args.face,
        face_db_path=args.face_db,
        face_model=args.face_model,
        face_threshold=args.face_threshold,
        profil=args.profil,
        organisation=args.organisation,
    )

    # Déterminer l'affichage
    show = not args.no_show if args.no_show else args.show
    if args.source == "0":
        show = True  # Toujours afficher pour la webcam

    # Lancer le pipeline
    face_status = "✅ Active" if pipeline.face_recognition_enabled else "❌ Désactivée"
    print(f"\n{'='*60}")
    print(f"  🎥 SURVEILLANCE-IA — Démarrage")
    print(f"{'='*60}")
    print(f"  Modèle        : {args.model}")
    print(f"  Source         : {args.source}")
    print(f"  Conf           : {args.conf}")
    print(f"  Timeout        : {args.timeout}s")
    print(f"  Alertes        : {args.alerts}s")
    print(f"  Ligne          : {args.line_position} ({args.line_orientation})")
    print(f"  Reconnaissance : {face_status}")
    if pipeline.face_recognition_enabled:
        n = len(pipeline.face_db.get_all_persons())
        print(f"  Personnes      : {n} enregistrée(s)")
        print(f"  Profil         : {args.profil}")
    print(f"{'='*60}")
    print(f"  [Q] Quitter | [R] Reset compteurs | [S] Snapshot")
    print(f"{'='*60}\n")

    report = pipeline.run(
        source=args.source,
        output_video=args.output,
        show=show,
        max_frames=args.max_frames,
    )

    # Afficher le résumé
    pipeline.print_summary(report)


if __name__ == "__main__":
    main()
