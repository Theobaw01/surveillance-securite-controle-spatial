"""
═══════════════════════════════════════════════════════════════
MODULE 8 — Base de données PostgreSQL (SQLAlchemy)
═══════════════════════════════════════════════════════════════
- Tables : events, alerts, daily_stats
- SQLAlchemy ORM avec modèles complets
- Fonctions CRUD
- Agrégations quotidiennes
═══════════════════════════════════════════════════════════════
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    Date,
    Text,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://surv_user:surv_pass@localhost:5432/surveillance_db",
)

Base = declarative_base()


# ═══════════════════════════════════════════════════════════════
# 1. MODÈLES ORM
# ═══════════════════════════════════════════════════════════════

class EventModel(Base):
    """
    Table des événements de passage.

    Champs :
    - id (PK)
    - person_id : ID unique de la personne (track_id)
    - direction : 'entry' ou 'exit'
    - line_name : Nom de la ligne virtuelle
    - timestamp : Horodatage Unix
    - datetime  : Date-heure lisible
    - confidence : Score de confiance de la détection
    - position_x, position_y : Position du centre
    - camera_id : Identifiant de la caméra
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # 'entry' | 'exit'
    line_name = Column(String(100), nullable=False)
    timestamp = Column(Float, nullable=False)
    event_datetime = Column(DateTime, nullable=False, index=True)
    confidence = Column(Float, default=0.0)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    camera_id = Column(String(50), default="cam_01")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "direction": self.direction,
            "line_name": self.line_name,
            "timestamp": self.timestamp,
            "datetime": self.event_datetime.isoformat() if self.event_datetime else None,
            "confidence": self.confidence,
            "position": {"x": self.position_x, "y": self.position_y},
            "camera_id": self.camera_id,
        }


class AlertModel(Base):
    """
    Table des alertes.

    Champs :
    - id (PK)
    - person_id : Personne concernée
    - alert_type : Type d'alerte (threshold_exceeded, loitering…)
    - threshold_seconds : Seuil déclenché
    - actual_seconds : Temps réel de présence
    - message : Description de l'alerte
    - acknowledged : Acquittée par un opérateur
    - camera_id : Caméra source
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)
    threshold_seconds = Column(Float, nullable=False)
    actual_seconds = Column(Float, nullable=False)
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, default=False)
    alert_datetime = Column(DateTime, nullable=False, index=True)
    camera_id = Column(String(50), default="cam_01")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "alert_type": self.alert_type,
            "threshold_seconds": self.threshold_seconds,
            "actual_seconds": round(self.actual_seconds, 2),
            "message": self.message,
            "acknowledged": self.acknowledged,
            "datetime": self.alert_datetime.isoformat() if self.alert_datetime else None,
            "camera_id": self.camera_id,
        }


class DailyStatsModel(Base):
    """
    Table des statistiques quotidiennes.

    Champs :
    - id (PK)
    - date : Date du jour
    - total_entries : Nombre total d'entrées
    - total_exits : Nombre total de sorties
    - peak_occupancy : Occupation maximale
    - avg_presence_time : Temps moyen de présence (s)
    - max_presence_time : Temps max de présence (s)
    - total_alerts : Nombre d'alertes
    - camera_id : Caméra
    """
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stats_date = Column(Date, nullable=False, index=True)
    total_entries = Column(Integer, default=0)
    total_exits = Column(Integer, default=0)
    peak_occupancy = Column(Integer, default=0)
    avg_presence_time = Column(Float, default=0.0)
    max_presence_time = Column(Float, default=0.0)
    min_presence_time = Column(Float, default=0.0)
    total_alerts = Column(Integer, default=0)
    total_unique_persons = Column(Integer, default=0)
    camera_id = Column(String(50), default="cam_01")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "date": self.stats_date.isoformat() if self.stats_date else None,
            "total_entries": self.total_entries,
            "total_exits": self.total_exits,
            "peak_occupancy": self.peak_occupancy,
            "avg_presence_time": round(self.avg_presence_time, 2),
            "max_presence_time": round(self.max_presence_time, 2),
            "min_presence_time": round(self.min_presence_time, 2),
            "total_alerts": self.total_alerts,
            "total_unique_persons": self.total_unique_persons,
            "camera_id": self.camera_id,
        }


# ═══════════════════════════════════════════════════════════════
# 2. GESTIONNAIRE DE BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════

class DatabaseManager:
    """
    Gestionnaire CRUD pour la base de données Surveillance-IA.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

    def create_tables(self) -> None:
        """Crée toutes les tables si elles n'existent pas."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("✅ Tables créées : events, alerts, daily_stats")

    def get_session(self) -> Session:
        """Retourne une nouvelle session."""
        return self.SessionLocal()

    # ─── EVENTS ─────────────────────────────────────────────────

    def insert_event(
        self,
        person_id: int,
        direction: str,
        line_name: str,
        timestamp: float,
        confidence: float = 0.0,
        position: tuple = (0, 0),
        camera_id: str = "cam_01",
    ) -> int:
        """Insère un événement de passage. Retourne l'ID."""
        session = self.get_session()
        try:
            event = EventModel(
                person_id=person_id,
                direction=direction,
                line_name=line_name,
                timestamp=timestamp,
                event_datetime=datetime.fromtimestamp(timestamp),
                confidence=confidence,
                position_x=position[0],
                position_y=position[1],
                camera_id=camera_id,
            )
            session.add(event)
            session.commit()
            return event.id
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur insertion event : {e}")
            raise
        finally:
            session.close()

    def get_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        direction: Optional[str] = None,
        camera_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Récupère les événements avec filtres."""
        session = self.get_session()
        try:
            query = session.query(EventModel)

            if start_date:
                query = query.filter(EventModel.event_datetime >= start_date)
            if end_date:
                query = query.filter(EventModel.event_datetime <= end_date)
            if direction:
                query = query.filter(EventModel.direction == direction)
            if camera_id:
                query = query.filter(EventModel.camera_id == camera_id)

            events = query.order_by(
                EventModel.event_datetime.desc()
            ).limit(limit).all()

            return [e.to_dict() for e in events]
        finally:
            session.close()

    def get_event_count(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        direction: Optional[str] = None,
    ) -> int:
        """Compte les événements avec filtres."""
        session = self.get_session()
        try:
            query = session.query(func.count(EventModel.id))
            if start_date:
                query = query.filter(EventModel.event_datetime >= start_date)
            if end_date:
                query = query.filter(EventModel.event_datetime <= end_date)
            if direction:
                query = query.filter(EventModel.direction == direction)
            return query.scalar() or 0
        finally:
            session.close()

    # ─── ALERTS ─────────────────────────────────────────────────

    def insert_alert(
        self,
        person_id: int,
        alert_type: str,
        threshold_seconds: float,
        actual_seconds: float,
        message: str,
        camera_id: str = "cam_01",
    ) -> int:
        """Insère une alerte. Retourne l'ID."""
        session = self.get_session()
        try:
            alert = AlertModel(
                person_id=person_id,
                alert_type=alert_type,
                threshold_seconds=threshold_seconds,
                actual_seconds=actual_seconds,
                message=message,
                alert_datetime=datetime.utcnow(),
                camera_id=camera_id,
            )
            session.add(alert)
            session.commit()
            return alert.id
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur insertion alert : {e}")
            raise
        finally:
            session.close()

    def get_alerts(
        self,
        unacknowledged_only: bool = False,
        limit: int = 50,
    ) -> List[Dict]:
        """Récupère les alertes."""
        session = self.get_session()
        try:
            query = session.query(AlertModel)
            if unacknowledged_only:
                query = query.filter(AlertModel.acknowledged == False)
            alerts = query.order_by(
                AlertModel.alert_datetime.desc()
            ).limit(limit).all()
            return [a.to_dict() for a in alerts]
        finally:
            session.close()

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Acquitte une alerte."""
        session = self.get_session()
        try:
            alert = session.query(AlertModel).filter(
                AlertModel.id == alert_id
            ).first()
            if alert:
                alert.acknowledged = True
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur acquittement : {e}")
            return False
        finally:
            session.close()

    # ─── DAILY STATS ────────────────────────────────────────────

    def insert_daily_stats(
        self,
        stats_date: date,
        total_entries: int = 0,
        total_exits: int = 0,
        peak_occupancy: int = 0,
        avg_presence_time: float = 0.0,
        max_presence_time: float = 0.0,
        min_presence_time: float = 0.0,
        total_alerts: int = 0,
        total_unique_persons: int = 0,
        camera_id: str = "cam_01",
    ) -> int:
        """Insère les stats quotidiennes."""
        session = self.get_session()
        try:
            stats = DailyStatsModel(
                stats_date=stats_date,
                total_entries=total_entries,
                total_exits=total_exits,
                peak_occupancy=peak_occupancy,
                avg_presence_time=avg_presence_time,
                max_presence_time=max_presence_time,
                min_presence_time=min_presence_time,
                total_alerts=total_alerts,
                total_unique_persons=total_unique_persons,
                camera_id=camera_id,
            )
            session.add(stats)
            session.commit()
            return stats.id
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur insertion daily_stats : {e}")
            raise
        finally:
            session.close()

    def get_daily_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        camera_id: Optional[str] = None,
    ) -> List[Dict]:
        """Récupère les stats quotidiennes."""
        session = self.get_session()
        try:
            query = session.query(DailyStatsModel)
            if start_date:
                query = query.filter(DailyStatsModel.stats_date >= start_date)
            if end_date:
                query = query.filter(DailyStatsModel.stats_date <= end_date)
            if camera_id:
                query = query.filter(DailyStatsModel.camera_id == camera_id)

            stats = query.order_by(DailyStatsModel.stats_date.desc()).all()
            return [s.to_dict() for s in stats]
        finally:
            session.close()

    def compute_daily_stats(
        self,
        target_date: Optional[date] = None,
        camera_id: str = "cam_01",
    ) -> Dict:
        """
        Calcule et enregistre les stats pour une journée.
        Si target_date=None, utilise aujourd'hui.
        """
        if target_date is None:
            target_date = date.today()

        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        session = self.get_session()
        try:
            # Compter entries/exits
            entries = session.query(func.count(EventModel.id)).filter(
                EventModel.event_datetime.between(start, end),
                EventModel.direction == "entry",
                EventModel.camera_id == camera_id,
            ).scalar() or 0

            exits = session.query(func.count(EventModel.id)).filter(
                EventModel.event_datetime.between(start, end),
                EventModel.direction == "exit",
                EventModel.camera_id == camera_id,
            ).scalar() or 0

            # Compter alertes
            alerts_count = session.query(func.count(AlertModel.id)).filter(
                AlertModel.alert_datetime.between(start, end),
                AlertModel.camera_id == camera_id,
            ).scalar() or 0

            # Personnes uniques
            unique_persons = session.query(
                func.count(func.distinct(EventModel.person_id))
            ).filter(
                EventModel.event_datetime.between(start, end),
                EventModel.camera_id == camera_id,
            ).scalar() or 0

            stats = {
                "date": target_date,
                "total_entries": entries,
                "total_exits": exits,
                "peak_occupancy": max(entries - exits, 0),
                "total_alerts": alerts_count,
                "total_unique_persons": unique_persons,
            }

            # Sauvegarder
            self.insert_daily_stats(
                stats_date=target_date,
                total_entries=entries,
                total_exits=exits,
                peak_occupancy=max(entries - exits, 0),
                total_alerts=alerts_count,
                total_unique_persons=unique_persons,
                camera_id=camera_id,
            )

            logger.info(
                f"✅ Stats calculées pour {target_date} : "
                f"IN={entries} OUT={exits} Alertes={alerts_count}"
            )

            return stats

        finally:
            session.close()


# ═══════════════════════════════════════════════════════════════
# 3. HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_db_manager(database_url: Optional[str] = None) -> DatabaseManager:
    """Factory pour le DatabaseManager."""
    db = DatabaseManager(database_url)
    db.create_tables()
    return db


def init_database(database_url: Optional[str] = None) -> None:
    """Initialise la base de données (création des tables)."""
    db = DatabaseManager(database_url)
    db.create_tables()
    logger.info("✅ Base de données initialisée")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Base de données — Surveillance-IA",
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Créer les tables",
    )
    parser.add_argument(
        "--url", default=None,
        help="URL de la base de données",
    )
    args = parser.parse_args()

    if args.init:
        init_database(args.url)
    else:
        parser.print_help()
