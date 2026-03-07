"""
═══════════════════════════════════════════════════════════════
MODULE 7 — Chronomètre de présence par personne
═══════════════════════════════════════════════════════════════
- Chronomètre individuel (entrée → sortie)
- Stockage : person_id, entry_time, exit_time, duration
- Alertes configurables (seuil de temps)
- Statistiques de temps de présence
═══════════════════════════════════════════════════════════════
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class PresenceRecord:
    """Enregistrement de présence d'une personne."""
    person_id: int
    entry_time: float
    exit_time: Optional[float] = None
    duration: Optional[float] = None  # secondes
    entry_datetime: str = ""
    exit_datetime: str = ""
    is_active: bool = True

    def __post_init__(self):
        self.entry_datetime = datetime.fromtimestamp(
            self.entry_time
        ).strftime("%Y-%m-%d %H:%M:%S")
        if self.exit_time is not None:
            self.close()

    def close(self) -> None:
        """Ferme la session de présence."""
        if self.exit_time is None:
            self.exit_time = time.time()
        self.duration = self.exit_time - self.entry_time
        self.exit_datetime = datetime.fromtimestamp(
            self.exit_time
        ).strftime("%Y-%m-%d %H:%M:%S")
        self.is_active = False

    @property
    def elapsed(self) -> float:
        """Temps écoulé depuis l'entrée (secondes)."""
        if self.exit_time:
            return self.exit_time - self.entry_time
        return time.time() - self.entry_time

    @property
    def elapsed_str(self) -> str:
        """Temps écoulé formaté (HH:MM:SS)."""
        return str(timedelta(seconds=int(self.elapsed)))

    def to_dict(self) -> Dict:
        """Sérialise l'enregistrement."""
        return {
            "person_id": self.person_id,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "duration": self.duration,
            "entry_datetime": self.entry_datetime,
            "exit_datetime": self.exit_datetime,
            "is_active": self.is_active,
            "elapsed": round(self.elapsed, 2),
            "elapsed_str": self.elapsed_str,
        }


@dataclass
class TimerAlert:
    """Alerte déclenchée par un seuil de temps."""
    person_id: int
    alert_type: str  # "threshold_exceeded", "long_presence", "loitering"
    threshold_seconds: float
    actual_seconds: float
    timestamp: float
    message: str
    acknowledged: bool = False


# ═══════════════════════════════════════════════════════════════
# 1. GESTIONNAIRE DE PRÉSENCE
# ═══════════════════════════════════════════════════════════════

class PresenceTimer:
    """
    Chronomètre de présence pour chaque personne détectée.

    Fonctionnalités :
    - Démarrage automatique à la première détection
    - Arrêt automatique quand la personne disparaît
    - Alertes sur seuils de temps configurables
    - Statistiques agrégées
    """

    def __init__(
        self,
        absence_timeout: float = 10.0,
        alert_thresholds: Optional[List[float]] = None,
        on_alert: Optional[Callable[[TimerAlert], None]] = None,
    ):
        """
        Args:
            absence_timeout: Durée (s) avant de considérer une personne partie.
            alert_thresholds: Seuils de temps (s) déclenchant des alertes.
                             Exemple : [300, 600, 1800] → alerte à 5min, 10min, 30min.
            on_alert: Callback appelé quand une alerte est déclenchée.
        """
        self.absence_timeout = absence_timeout
        self.alert_thresholds = alert_thresholds or [300, 600, 1800]
        self.on_alert = on_alert

        # Sessions actives : person_id → PresenceRecord
        self._active_sessions: Dict[int, PresenceRecord] = {}

        # Historique complet
        self._completed_sessions: List[PresenceRecord] = []

        # Dernière détection par ID
        self._last_seen: Dict[int, float] = {}

        # Alertes déjà déclenchées (pour éviter les doublons)
        self._triggered_alerts: Dict[int, set] = defaultdict(set)

        # Toutes les alertes
        self._alerts: List[TimerAlert] = []

        logger.info(
            f"✅ PresenceTimer initialisé | "
            f"timeout={absence_timeout}s | "
            f"seuils={alert_thresholds}"
        )

    def update(self, active_track_ids: List[int]) -> List[TimerAlert]:
        """
        Met à jour les chronomètres avec les IDs actuellement visibles.

        Args:
            active_track_ids: Liste des track_ids détectés dans la frame courante.

        Returns:
            Nouvelles alertes déclenchées.
        """
        now = time.time()
        new_alerts = []

        # 1. Mettre à jour les personnes présentes
        for track_id in active_track_ids:
            self._last_seen[track_id] = now

            if track_id not in self._active_sessions:
                # Nouvelle personne → démarrer le chronomètre
                record = PresenceRecord(
                    person_id=track_id,
                    entry_time=now,
                )
                self._active_sessions[track_id] = record
                logger.info(
                    f"  ⏱️ ID:{track_id} → ENTRÉE à "
                    f"{record.entry_datetime}"
                )

            # Vérifier les seuils d'alerte
            session = self._active_sessions[track_id]
            elapsed = session.elapsed
            for threshold in self.alert_thresholds:
                if (
                    elapsed >= threshold
                    and threshold not in self._triggered_alerts[track_id]
                ):
                    alert = TimerAlert(
                        person_id=track_id,
                        alert_type="threshold_exceeded",
                        threshold_seconds=threshold,
                        actual_seconds=elapsed,
                        timestamp=now,
                        message=(
                            f"Personne ID:{track_id} présente depuis "
                            f"{timedelta(seconds=int(elapsed))} "
                            f"(seuil: {timedelta(seconds=int(threshold))})"
                        ),
                    )
                    self._triggered_alerts[track_id].add(threshold)
                    self._alerts.append(alert)
                    new_alerts.append(alert)

                    logger.warning(f"  ⚠️ ALERTE : {alert.message}")

                    if self.on_alert:
                        self.on_alert(alert)

        # 2. Fermer les sessions des personnes disparues
        disappeared_ids = []
        for track_id, session in self._active_sessions.items():
            last = self._last_seen.get(track_id, 0)
            if now - last > self.absence_timeout:
                session.close()
                self._completed_sessions.append(session)
                disappeared_ids.append(track_id)

                logger.info(
                    f"  ⏱️ ID:{track_id} → SORTIE | "
                    f"Durée: {session.elapsed_str}"
                )

        # Nettoyer les sessions fermées
        for track_id in disappeared_ids:
            del self._active_sessions[track_id]
            self._triggered_alerts.pop(track_id, None)

        return new_alerts

    # ─── Accesseurs ─────────────────────────────────────────────

    def get_active_sessions(self) -> Dict[int, Dict]:
        """Retourne les sessions actuellement actives."""
        return {
            tid: session.to_dict()
            for tid, session in self._active_sessions.items()
        }

    def get_completed_sessions(self) -> List[Dict]:
        """Retourne l'historique des sessions terminées."""
        return [s.to_dict() for s in self._completed_sessions]

    def get_all_sessions(self) -> List[Dict]:
        """Retourne toutes les sessions (actives + terminées)."""
        all_sessions = []
        for session in self._active_sessions.values():
            all_sessions.append(session.to_dict())
        for session in self._completed_sessions:
            all_sessions.append(session.to_dict())
        return all_sessions

    def get_alerts(self, unacknowledged_only: bool = False) -> List[Dict]:
        """Retourne les alertes."""
        alerts = self._alerts
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]
        return [
            {
                "person_id": a.person_id,
                "alert_type": a.alert_type,
                "threshold_seconds": a.threshold_seconds,
                "actual_seconds": round(a.actual_seconds, 2),
                "timestamp": a.timestamp,
                "message": a.message,
                "acknowledged": a.acknowledged,
                "datetime": datetime.fromtimestamp(a.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
            for a in alerts
        ]

    def get_statistics(self) -> Dict:
        """Calcule les statistiques de présence."""
        completed = self._completed_sessions
        durations = [s.duration for s in completed if s.duration is not None]

        if not durations:
            return {
                "total_sessions": 0,
                "active_sessions": len(self._active_sessions),
                "avg_duration": 0,
                "min_duration": 0,
                "max_duration": 0,
                "median_duration": 0,
                "total_alerts": len(self._alerts),
            }

        durations.sort()
        n = len(durations)

        return {
            "total_sessions": len(completed),
            "active_sessions": len(self._active_sessions),
            "avg_duration": round(sum(durations) / n, 2),
            "min_duration": round(min(durations), 2),
            "max_duration": round(max(durations), 2),
            "median_duration": round(
                durations[n // 2] if n % 2 else
                (durations[n // 2 - 1] + durations[n // 2]) / 2,
                2,
            ),
            "avg_duration_str": str(
                timedelta(seconds=int(sum(durations) / n))
            ),
            "total_alerts": len(self._alerts),
        }

    def acknowledge_alert(self, index: int) -> bool:
        """Acquitte une alerte par son index."""
        if 0 <= index < len(self._alerts):
            self._alerts[index].acknowledged = True
            return True
        return False

    def reset(self) -> None:
        """Réinitialise tous les chronomètres."""
        self._active_sessions.clear()
        self._completed_sessions.clear()
        self._last_seen.clear()
        self._triggered_alerts.clear()
        self._alerts.clear()
        logger.info("🔄 PresenceTimer réinitialisé")
