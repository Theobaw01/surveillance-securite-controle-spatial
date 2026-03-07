"""
═══════════════════════════════════════════════════════════════
MODULE 5 — Tracking multi-personnes (ByteTrack)
═══════════════════════════════════════════════════════════════
- ByteTrack intégré via YOLO v8 (tracker natif)
- Attribution d'IDs uniques et persistants
- Gestion des occlusions et ré-identification
- Suivi des trajectoires pour analyse
- Temps réel sur flux vidéo
═══════════════════════════════════════════════════════════════
"""

import os
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field

import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrackedPerson:
    """Représente une personne suivie."""
    track_id: int
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    class_id: int = 0
    center: Tuple[int, int] = (0, 0)

    # Historique
    first_seen: float = 0.0
    last_seen: float = 0.0
    frame_count: int = 0
    trajectory: List[Tuple[int, int]] = field(default_factory=list)

    def __post_init__(self):
        # Calculer le centre
        x1, y1, x2, y2 = self.bbox
        self.center = ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class TrackingFrame:
    """Résultat du tracking pour une frame."""
    frame_id: int
    timestamp: float
    persons: List[TrackedPerson]
    total_detected: int
    fps: float
    annotated_frame: Optional[np.ndarray] = None


# ═══════════════════════════════════════════════════════════════
# 1. TRACKER PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class PersonTracker:
    """
    Tracker multi-personnes basé sur ByteTrack (intégré YOLO v8).

    Fonctionnalités :
    - IDs uniques et persistants entre les frames
    - Gestion des occlusions (tracks perdus temporairement)
    - Ré-identification via ByteTrack (association basses confiances)
    - Trajectoires complètes pour analyse
    """

    def __init__(
        self,
        model_path: str,
        conf_threshold: float = 0.3,
        iou_threshold: float = 0.5,
        tracker_type: str = "bytetrack.yaml",
        max_trajectory_length: int = 300,
        person_class_id: int = 0,
    ):
        """
        Args:
            model_path: Chemin vers le best.pt YOLO fine-tuné.
            conf_threshold: Seuil de confiance minimal.
            iou_threshold: Seuil IoU pour le NMS.
            tracker_type: Fichier config tracker (bytetrack.yaml).
            max_trajectory_length: Longueur max des trajectoires.
            person_class_id: ID de la classe « person ».
        """
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("ultralytics non installé")

        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.tracker_type = tracker_type
        self.max_trajectory_length = max_trajectory_length
        self.person_class_id = person_class_id

        # État interne
        self._active_tracks: Dict[int, TrackedPerson] = {}
        self._lost_tracks: Dict[int, TrackedPerson] = {}
        self._all_tracks: Dict[int, TrackedPerson] = {}
        self._trajectories: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=max_trajectory_length)
        )
        self._frame_count = 0
        self._start_time = time.time()

        # Couleurs pour la visualisation (par ID)
        self._colors = self._generate_colors(200)

        logger.info(
            f"✅ PersonTracker initialisé | "
            f"Modèle: {model_path} | Tracker: {tracker_type}"
        )

    def _generate_colors(self, n: int) -> List[Tuple[int, int, int]]:
        """Génère des couleurs distinctes pour chaque ID."""
        colors = []
        for i in range(n):
            hue = int(180 * i / n)
            color = cv2.cvtColor(
                np.array([[[hue, 255, 200]]], dtype=np.uint8),
                cv2.COLOR_HSV2BGR,
            )[0][0]
            colors.append(tuple(int(c) for c in color))
        return colors

    def track_frame(
        self,
        frame: np.ndarray,
        draw: bool = True,
    ) -> TrackingFrame:
        """
        Détecte et suit les personnes dans une frame.

        Args:
            frame: Image BGR (OpenCV).
            draw: Annoter la frame avec les détections/trajectoires.

        Returns:
            TrackingFrame avec toutes les informations de tracking.
        """
        self._frame_count += 1
        timestamp = time.time()

        # Détection + Tracking YOLO v8 avec ByteTrack
        results = self.model.track(
            source=frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            tracker=self.tracker_type,
            persist=True,
            verbose=False,
            classes=[self.person_class_id],
        )

        persons = []
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    # Extraire les données
                    bbox = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = bbox

                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])

                    # Track ID (ByteTrack)
                    track_id = -1
                    if box.id is not None:
                        track_id = int(box.id[0])

                    # Créer ou mettre à jour la personne suivie
                    person = TrackedPerson(
                        track_id=track_id,
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_id=cls_id,
                        last_seen=timestamp,
                    )

                    # Mettre à jour l'historique
                    if track_id >= 0:
                        if track_id in self._all_tracks:
                            prev = self._all_tracks[track_id]
                            person.first_seen = prev.first_seen
                            person.frame_count = prev.frame_count + 1
                        else:
                            person.first_seen = timestamp
                            person.frame_count = 1

                        self._all_tracks[track_id] = person
                        self._active_tracks[track_id] = person

                        # Ajouter à la trajectoire
                        self._trajectories[track_id].append(person.center)

                    persons.append(person)

        # FPS
        elapsed = time.time() - self._start_time
        fps = self._frame_count / max(elapsed, 0.001)

        # Annoter la frame
        annotated = None
        if draw:
            annotated = self._draw_annotations(frame, persons)

        return TrackingFrame(
            frame_id=self._frame_count,
            timestamp=timestamp,
            persons=persons,
            total_detected=len(persons),
            fps=fps,
            annotated_frame=annotated,
        )

    def _draw_annotations(
        self,
        frame: np.ndarray,
        persons: List[TrackedPerson],
    ) -> np.ndarray:
        """Dessine les annotations de tracking sur la frame."""
        annotated = frame.copy()

        for person in persons:
            x1, y1, x2, y2 = person.bbox
            track_id = person.track_id

            # Couleur par ID
            color = self._colors[track_id % len(self._colors)] if track_id >= 0 else (0, 255, 0)

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Label
            label = f"ID:{track_id} {person.confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(
                annotated,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                color, -1,
            )
            cv2.putText(
                annotated, label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2,
            )

            # Trajectoire
            if track_id >= 0 and track_id in self._trajectories:
                trajectory = list(self._trajectories[track_id])
                if len(trajectory) > 1:
                    for i in range(1, len(trajectory)):
                        # Fade progressif
                        alpha = i / len(trajectory)
                        thickness = max(1, int(3 * alpha))
                        cv2.line(
                            annotated,
                            trajectory[i - 1],
                            trajectory[i],
                            color,
                            thickness,
                        )

        # Overlay info
        info_text = (
            f"Personnes: {len(persons)} | "
            f"Total IDs: {len(self._all_tracks)} | "
            f"FPS: {self._frame_count / max(time.time() - self._start_time, 0.001):.1f}"
        )
        cv2.rectangle(annotated, (0, 0), (len(info_text) * 11, 35), (0, 0, 0), -1)
        cv2.putText(
            annotated, info_text,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
            (0, 255, 0), 2,
        )

        return annotated

    # ─── Accesseurs ─────────────────────────────────────────────

    def get_active_tracks(self) -> Dict[int, TrackedPerson]:
        """Retourne les tracks actuellement actifs."""
        return dict(self._active_tracks)

    def get_all_tracks(self) -> Dict[int, TrackedPerson]:
        """Retourne tous les tracks (historique complet)."""
        return dict(self._all_tracks)

    def get_trajectory(self, track_id: int) -> List[Tuple[int, int]]:
        """Retourne la trajectoire d'un track donné."""
        return list(self._trajectories.get(track_id, []))

    def get_total_unique_persons(self) -> int:
        """Retourne le nombre total de personnes uniques détectées."""
        return len(self._all_tracks)

    def reset(self) -> None:
        """Réinitialise le tracker."""
        self._active_tracks.clear()
        self._lost_tracks.clear()
        self._all_tracks.clear()
        self._trajectories.clear()
        self._frame_count = 0
        self._start_time = time.time()
        logger.info("🔄 Tracker réinitialisé")


# ═══════════════════════════════════════════════════════════════
# 2. TRACKING VIDÉO COMPLET
# ═══════════════════════════════════════════════════════════════

class VideoTracker:
    """
    Pipeline complète de tracking sur fichier vidéo ou flux caméra.
    """

    def __init__(
        self,
        tracker: PersonTracker,
        output_dir: str = "outputs/tracking",
    ):
        self.tracker = tracker
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def process_video(
        self,
        source: str,
        output_video: Optional[str] = None,
        show: bool = False,
        max_frames: Optional[int] = None,
    ) -> Dict:
        """
        Traite une vidéo complète ou flux caméra.

        Args:
            source: Chemin vidéo, URL RTSP, ou index caméra ("0").
            output_video: Chemin de la vidéo annotée en sortie.
            show: Afficher en temps réel.
            max_frames: Nombre max de frames à traiter.

        Returns:
            Statistiques de tracking.
        """
        # Déterminer la source
        if source.isdigit():
            cap = cv2.VideoCapture(int(source))
        else:
            cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            raise ValueError(f"Impossible d'ouvrir la source : {source}")

        # Propriétés vidéo
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logger.info(
            f"Source: {source} | {width}x{height} | "
            f"{fps:.1f} FPS | {total_frames} frames"
        )

        # Writer vidéo de sortie
        writer = None
        if output_video:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(
                output_video, fourcc, fps, (width, height)
            )

        # Tracking
        self.tracker.reset()
        frame_count = 0
        all_frame_results = []

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if max_frames and frame_count >= max_frames:
                    break

                # Tracker la frame
                result = self.tracker.track_frame(frame, draw=True)
                all_frame_results.append({
                    "frame_id": result.frame_id,
                    "detected": result.total_detected,
                    "persons": [
                        {
                            "id": p.track_id,
                            "bbox": list(p.bbox),
                            "conf": round(p.confidence, 3),
                            "center": list(p.center),
                        }
                        for p in result.persons
                    ],
                })

                # Écrire la frame annotée
                if writer and result.annotated_frame is not None:
                    writer.write(result.annotated_frame)

                # Afficher
                if show and result.annotated_frame is not None:
                    cv2.imshow("Surveillance-IA Tracking", result.annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                frame_count += 1

                if frame_count % 100 == 0:
                    logger.info(
                        f"  Frame {frame_count}/{total_frames} | "
                        f"Personnes actives: {result.total_detected} | "
                        f"FPS: {result.fps:.1f}"
                    )

        finally:
            cap.release()
            if writer:
                writer.release()
            if show:
                cv2.destroyAllWindows()

        # Statistiques finales
        stats = {
            "source": source,
            "total_frames": frame_count,
            "total_unique_persons": self.tracker.get_total_unique_persons(),
            "output_video": output_video,
            "frame_results": all_frame_results,
        }

        logger.info(
            f"✅ Tracking terminé | {frame_count} frames | "
            f"{stats['total_unique_persons']} personnes uniques"
        )

        return stats

    def generate_heatmap(
        self,
        width: int = 1920,
        height: int = 1080,
        save_path: Optional[str] = None,
    ) -> np.ndarray:
        """
        Génère une heatmap des trajectoires accumulées.

        Returns:
            Image de la heatmap (BGR).
        """
        heatmap = np.zeros((height, width), dtype=np.float32)

        for track_id, trajectory in self.tracker._trajectories.items():
            for point in trajectory:
                x, y = point
                if 0 <= x < width and 0 <= y < height:
                    cv2.circle(heatmap, (x, y), 15, 1, -1)

        # Normaliser et coloriser
        if heatmap.max() > 0:
            heatmap = heatmap / heatmap.max()
        heatmap_colored = cv2.applyColorMap(
            (heatmap * 255).astype(np.uint8),
            cv2.COLORMAP_JET,
        )

        if save_path:
            cv2.imwrite(save_path, heatmap_colored)
            logger.info(f"🔥 Heatmap sauvegardée : {save_path}")

        return heatmap_colored


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Tracking multi-personnes — Surveillance-IA",
    )

    parser.add_argument("--model", required=True, help="Chemin vers best.pt")
    parser.add_argument(
        "--source", default="0",
        help="Source vidéo : chemin fichier, URL RTSP, ou '0' pour webcam",
    )
    parser.add_argument("--output", default=None, help="Vidéo annotée de sortie")
    parser.add_argument("--conf", type=float, default=0.3)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--show", action="store_true", help="Afficher temps réel")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument(
        "--heatmap", default=None, help="Chemin pour sauver la heatmap"
    )

    args = parser.parse_args()

    # Initialiser le tracker
    tracker = PersonTracker(
        model_path=args.model,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
    )

    video_tracker = VideoTracker(tracker)

    # Lancer le tracking
    stats = video_tracker.process_video(
        source=args.source,
        output_video=args.output,
        show=args.show,
        max_frames=args.max_frames,
    )

    # Générer la heatmap
    if args.heatmap:
        video_tracker.generate_heatmap(save_path=args.heatmap)


if __name__ == "__main__":
    main()
