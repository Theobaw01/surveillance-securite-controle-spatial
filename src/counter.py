"""
═══════════════════════════════════════════════════════════════
MODULE 6 — Comptage de personnes (entrées / sorties)
═══════════════════════════════════════════════════════════════
- Définition de lignes virtuelles (configurable)
- Comptage directionnel (entrées ↑ / sorties ↓)
- Overlay temps réel sur le flux vidéo
- Historique horodaté de chaque passage
═══════════════════════════════════════════════════════════════
"""

import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

import cv2
import numpy as np

from src.tracker import TrackedPerson, TrackingFrame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES & ENUMS
# ═══════════════════════════════════════════════════════════════

class Direction(Enum):
    """Direction de passage."""
    ENTRY = "entry"
    EXIT = "exit"
    UNKNOWN = "unknown"


@dataclass
class VirtualLine:
    """
    Ligne virtuelle de comptage.

    Définition : deux points (x1,y1) → (x2,y2)
    Direction : entrée = traversée du haut vers le bas (ou gauche→droite)
    """
    name: str
    point1: Tuple[int, int]
    point2: Tuple[int, int]
    entry_direction: str = "down"  # "down", "up", "left", "right"
    color: Tuple[int, int, int] = (0, 255, 255)  # Jaune
    thickness: int = 3

    @property
    def midpoint(self) -> Tuple[int, int]:
        return (
            (self.point1[0] + self.point2[0]) // 2,
            (self.point1[1] + self.point2[1]) // 2,
        )

    @property
    def is_horizontal(self) -> bool:
        return abs(self.point2[1] - self.point1[1]) < abs(self.point2[0] - self.point1[0])


@dataclass
class PassageEvent:
    """Événement de passage d'une personne."""
    track_id: int
    direction: Direction
    line_name: str
    timestamp: float
    datetime_str: str
    position: Tuple[int, int]
    confidence: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 1. COMPTEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class PersonCounter:
    """
    Compteur directionnel de personnes basé sur le croisement
    de lignes virtuelles.

    Fonctionnalités :
    - Lignes virtuelles configurables (position, direction)
    - Comptage IN / OUT par ligne
    - Historique horodaté de chaque passage
    - Overlay temps réel
    """

    def __init__(
        self,
        lines: Optional[List[VirtualLine]] = None,
        crossing_margin: int = 20,
    ):
        """
        Args:
            lines: Liste de lignes virtuelles de comptage.
            crossing_margin: Marge (px) autour de la ligne pour détecter le croisement.
        """
        self.lines = lines or []
        self.crossing_margin = crossing_margin

        # Compteurs par ligne
        self._entry_count: Dict[str, int] = defaultdict(int)
        self._exit_count: Dict[str, int] = defaultdict(int)

        # Historique des passages
        self._passage_history: List[PassageEvent] = []

        # État des tracks (positions précédentes)
        self._prev_positions: Dict[int, Tuple[int, int]] = {}

        # Tracks déjà comptés (pour éviter les doublons)
        self._counted_tracks: Dict[str, set] = defaultdict(set)

        logger.info(
            f"✅ PersonCounter initialisé | "
            f"{len(self.lines)} ligne(s) virtuelle(s)"
        )

    def add_line(
        self,
        name: str,
        point1: Tuple[int, int],
        point2: Tuple[int, int],
        entry_direction: str = "down",
    ) -> None:
        """Ajoute une ligne virtuelle de comptage."""
        line = VirtualLine(
            name=name,
            point1=point1,
            point2=point2,
            entry_direction=entry_direction,
        )
        self.lines.append(line)
        logger.info(
            f"  Ligne ajoutée : '{name}' "
            f"({point1} → {point2}) | direction={entry_direction}"
        )

    def add_horizontal_line(
        self,
        name: str,
        y: int,
        x_start: int = 0,
        x_end: int = 1920,
        entry_direction: str = "down",
    ) -> None:
        """Raccourci pour ajouter une ligne horizontale."""
        self.add_line(name, (x_start, y), (x_end, y), entry_direction)

    def add_vertical_line(
        self,
        name: str,
        x: int,
        y_start: int = 0,
        y_end: int = 1080,
        entry_direction: str = "right",
    ) -> None:
        """Raccourci pour ajouter une ligne verticale."""
        self.add_line(name, (x, y_start), (x, y_end), entry_direction)

    def update(
        self,
        tracking_result: TrackingFrame,
    ) -> List[PassageEvent]:
        """
        Met à jour les compteurs avec le résultat du tracking.

        Args:
            tracking_result: Résultat du tracker pour la frame courante.

        Returns:
            Liste des nouveaux événements de passage.
        """
        new_events = []

        for person in tracking_result.persons:
            track_id = person.track_id
            if track_id < 0:
                continue

            current_pos = person.center
            prev_pos = self._prev_positions.get(track_id)

            if prev_pos is not None:
                # Vérifier le croisement de chaque ligne
                for line in self.lines:
                    event = self._check_crossing(
                        track_id, prev_pos, current_pos,
                        line, person.confidence,
                    )
                    if event:
                        new_events.append(event)

            # Mémoriser la position actuelle
            self._prev_positions[track_id] = current_pos

        return new_events

    def _check_crossing(
        self,
        track_id: int,
        prev_pos: Tuple[int, int],
        curr_pos: Tuple[int, int],
        line: VirtualLine,
        confidence: float,
    ) -> Optional[PassageEvent]:
        """
        Vérifie si un track a croisé une ligne virtuelle entre deux frames.
        """
        # Éviter le comptage double
        if track_id in self._counted_tracks[line.name]:
            return None

        # Déterminer si la ligne est horizontale ou verticale
        if line.is_horizontal:
            # Ligne horizontale → vérifier le croisement vertical
            line_y = (line.point1[1] + line.point2[1]) // 2
            line_x_min = min(line.point1[0], line.point2[0])
            line_x_max = max(line.point1[0], line.point2[0])

            # Le centre doit être dans la plage X de la ligne
            if not (line_x_min <= curr_pos[0] <= line_x_max):
                return None

            # Vérifier le croisement
            crossed = (
                (prev_pos[1] < line_y and curr_pos[1] >= line_y) or
                (prev_pos[1] > line_y and curr_pos[1] <= line_y)
            )

            if not crossed:
                return None

            # Déterminer la direction
            moving_down = curr_pos[1] > prev_pos[1]

            if line.entry_direction == "down":
                direction = Direction.ENTRY if moving_down else Direction.EXIT
            else:
                direction = Direction.EXIT if moving_down else Direction.ENTRY

        else:
            # Ligne verticale → vérifier le croisement horizontal
            line_x = (line.point1[0] + line.point2[0]) // 2
            line_y_min = min(line.point1[1], line.point2[1])
            line_y_max = max(line.point1[1], line.point2[1])

            if not (line_y_min <= curr_pos[1] <= line_y_max):
                return None

            crossed = (
                (prev_pos[0] < line_x and curr_pos[0] >= line_x) or
                (prev_pos[0] > line_x and curr_pos[0] <= line_x)
            )

            if not crossed:
                return None

            moving_right = curr_pos[0] > prev_pos[0]

            if line.entry_direction == "right":
                direction = Direction.ENTRY if moving_right else Direction.EXIT
            else:
                direction = Direction.EXIT if moving_right else Direction.ENTRY

        # Incrémenter les compteurs
        if direction == Direction.ENTRY:
            self._entry_count[line.name] += 1
        else:
            self._exit_count[line.name] += 1

        # Marquer comme compté
        self._counted_tracks[line.name].add(track_id)

        # Créer l'événement
        now = time.time()
        event = PassageEvent(
            track_id=track_id,
            direction=direction,
            line_name=line.name,
            timestamp=now,
            datetime_str=datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
            position=curr_pos,
            confidence=confidence,
        )

        self._passage_history.append(event)

        logger.info(
            f"  🚶 [{line.name}] ID:{track_id} → "
            f"{direction.value.upper()} | "
            f"IN={self._entry_count[line.name]} "
            f"OUT={self._exit_count[line.name]}"
        )

        return event

    def draw_overlay(
        self,
        frame: np.ndarray,
        show_counters: bool = True,
        show_lines: bool = True,
    ) -> np.ndarray:
        """
        Dessine les lignes virtuelles et les compteurs sur la frame.

        Returns:
            Frame annotée.
        """
        annotated = frame.copy()

        if show_lines:
            for line in self.lines:
                # Ligne virtuelle
                cv2.line(
                    annotated,
                    line.point1, line.point2,
                    line.color, line.thickness,
                )

                # Flèche indiquant la direction d'entrée
                mid = line.midpoint
                arrow_len = 30
                if line.entry_direction == "down":
                    end = (mid[0], mid[1] + arrow_len)
                elif line.entry_direction == "up":
                    end = (mid[0], mid[1] - arrow_len)
                elif line.entry_direction == "right":
                    end = (mid[0] + arrow_len, mid[1])
                else:
                    end = (mid[0] - arrow_len, mid[1])
                cv2.arrowedLine(annotated, mid, end, line.color, 2)

                # Label de la ligne
                cv2.putText(
                    annotated, line.name,
                    (line.point1[0] + 10, line.point1[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    line.color, 2,
                )

        if show_counters:
            # Panneau de comptage
            panel_height = 40 + len(self.lines) * 30
            cv2.rectangle(
                annotated,
                (10, frame.shape[0] - panel_height - 10),
                (350, frame.shape[0] - 10),
                (0, 0, 0), -1,
            )

            y_offset = frame.shape[0] - panel_height + 10
            cv2.putText(
                annotated, "COMPTEURS",
                (20, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2,
            )
            y_offset += 30

            for line in self.lines:
                entries = self._entry_count[line.name]
                exits = self._exit_count[line.name]
                occupancy = entries - exits

                text = f"{line.name}: IN={entries} OUT={exits} [{occupancy}]"
                color = (0, 255, 0) if occupancy >= 0 else (0, 0, 255)

                cv2.putText(
                    annotated, text,
                    (20, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    color, 1,
                )
                y_offset += 25

        return annotated

    # ─── Accesseurs ─────────────────────────────────────────────

    def get_counts(self) -> Dict[str, Dict[str, int]]:
        """Retourne les compteurs par ligne."""
        result = {}
        for line in self.lines:
            entries = self._entry_count[line.name]
            exits = self._exit_count[line.name]
            result[line.name] = {
                "entries": entries,
                "exits": exits,
                "occupancy": entries - exits,
            }
        return result

    def get_total_entries(self) -> int:
        """Total des entrées toutes lignes confondues."""
        return sum(self._entry_count.values())

    def get_total_exits(self) -> int:
        """Total des sorties toutes lignes confondues."""
        return sum(self._exit_count.values())

    def get_current_occupancy(self) -> int:
        """Occupation actuelle (entrées - sorties)."""
        return self.get_total_entries() - self.get_total_exits()

    def get_passage_history(self) -> List[Dict]:
        """Retourne l'historique horodaté des passages."""
        return [
            {
                "track_id": e.track_id,
                "direction": e.direction.value,
                "line": e.line_name,
                "timestamp": e.timestamp,
                "datetime": e.datetime_str,
                "position": e.position,
                "confidence": e.confidence,
            }
            for e in self._passage_history
        ]

    def get_hourly_histogram(self) -> Dict[str, Dict[str, int]]:
        """
        Histogramme des passages par heure.

        Returns:
            {"HH:00": {"entries": n, "exits": n}, ...}
        """
        histogram: Dict[str, Dict[str, int]] = {}

        for event in self._passage_history:
            hour_key = datetime.fromtimestamp(
                event.timestamp
            ).strftime("%H:00")

            if hour_key not in histogram:
                histogram[hour_key] = {"entries": 0, "exits": 0}

            if event.direction == Direction.ENTRY:
                histogram[hour_key]["entries"] += 1
            else:
                histogram[hour_key]["exits"] += 1

        return dict(sorted(histogram.items()))

    def reset(self) -> None:
        """Réinitialise les compteurs."""
        self._entry_count.clear()
        self._exit_count.clear()
        self._passage_history.clear()
        self._prev_positions.clear()
        self._counted_tracks.clear()
        logger.info("🔄 Compteurs réinitialisés")
