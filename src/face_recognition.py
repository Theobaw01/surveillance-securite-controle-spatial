"""
═══════════════════════════════════════════════════════════════
MODULE 9 — Reconnaissance Faciale Universelle (InsightFace Buffalo)
═══════════════════════════════════════════════════════════════
- InsightFace Buffalo_l : détection + reconnaissance faciale
- Encodage facial (embeddings 512D)
- Matching visages connus vs inconnus
- Enrôlement dynamique (ajout de nouveaux visages)
- Base SQLite locale pour les embeddings
- Système universel: écoles, entreprises, événements, bâtiments...
- Enregistrement de personnes avec métadonnées flexibles
═══════════════════════════════════════════════════════════════
"""

import os
import json
import time
import logging
import sqlite3
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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
class FaceInfo:
    """Informations d'un visage détecté."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    embedding: np.ndarray            # vecteur 512D
    confidence: float                # score de détection
    landmarks: Optional[np.ndarray] = None  # 5 points du visage
    age: Optional[int] = None
    gender: Optional[str] = None     # 'M' ou 'F'


@dataclass
class IdentifiedPerson:
    """Personne identifiée par reconnaissance faciale."""
    person_id: str                   # ID unique dans la base
    nom: str
    prenom: str
    groupe: str = ""                 # classe, département, équipe...
    role: str = "visiteur"           # visiteur, employe, eleve, admin, vip...
    organisation: str = ""           # entreprise, école, club...
    photo_path: str = ""
    similarity: float = 0.0          # score de similarité (0-1)
    face_bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    metadata: Dict = field(default_factory=dict)  # champs libres

    # Backward compatibility
    @property
    def classe(self) -> str:
        return self.groupe

    @property
    def full_name(self) -> str:
        return f"{self.prenom} {self.nom}"

    @property
    def display_label(self) -> str:
        """Label d'affichage contextuel."""
        parts = [self.full_name]
        if self.groupe:
            parts.append(f"({self.groupe})")
        elif self.organisation:
            parts.append(f"[{self.organisation}]")
        return " ".join(parts)


# ═══════════════════════════════════════════════════════════════
# 1. BASE DE DONNÉES DES VISAGES (SQLite)
# ═══════════════════════════════════════════════════════════════

class FaceDatabase:
    """
    Base de données SQLite pour stocker les visages connus.

    Système universel utilisable partout :
    - Écoles (élèves, professeurs, personnel)
    - Entreprises (employés, visiteurs)
    - Événements (participants, staff, VIP)
    - Bâtiments (résidents, livreurs)

    Tables :
    - persons     : infos personnelles (nom, prénom, groupe, rôle, organisation...)
    - embeddings  : vecteurs faciaux (512D) par personne
    - attendance  : historique des pointages (entrées/sorties)
    """

    def __init__(self, db_path: str = "data/faces.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._run_migrations()

        # Cache en mémoire pour les embeddings (performance)
        self._embeddings_cache: Dict[str, List[np.ndarray]] = {}
        self._persons_cache: Dict[str, Dict] = {}
        self._load_cache()

        logger.info(
            f"✅ FaceDatabase initialisée | {db_path} | "
            f"{len(self._persons_cache)} personne(s) enregistrée(s)"
        )

    def _create_tables(self):
        """Crée les tables si elles n'existent pas."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS persons (
                person_id    TEXT PRIMARY KEY,
                nom          TEXT NOT NULL,
                prenom       TEXT NOT NULL,
                groupe       TEXT DEFAULT '',
                role         TEXT DEFAULT 'visiteur',
                organisation TEXT DEFAULT '',
                date_naissance TEXT DEFAULT '',
                email        TEXT DEFAULT '',
                telephone    TEXT DEFAULT '',
                photo_path   TEXT DEFAULT '',
                heure_arrivee_prevue TEXT DEFAULT '',
                heure_depart_prevue  TEXT DEFAULT '',
                notes        TEXT DEFAULT '',
                tags         TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                actif        INTEGER DEFAULT 1,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                updated_at   TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id    TEXT NOT NULL,
                embedding    BLOB NOT NULL,
                source       TEXT DEFAULT 'enrollment',
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (person_id) REFERENCES persons(person_id)
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id    TEXT NOT NULL,
                nom          TEXT DEFAULT '',
                prenom       TEXT DEFAULT '',
                direction    TEXT NOT NULL,
                timestamp    REAL NOT NULL,
                datetime_str TEXT NOT NULL,
                similarity   REAL DEFAULT 0.0,
                camera_id    TEXT DEFAULT 'cam_01',
                is_late      INTEGER DEFAULT 0,
                retard_minutes REAL DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (person_id) REFERENCES persons(person_id)
            );

            CREATE INDEX IF NOT EXISTS idx_attendance_person
                ON attendance(person_id);
            CREATE INDEX IF NOT EXISTS idx_attendance_date
                ON attendance(datetime_str);
            CREATE INDEX IF NOT EXISTS idx_embeddings_person
                ON embeddings(person_id);
        """)
        self.conn.commit()

    def _run_migrations(self):
        """Applique les migrations de schéma pour les bases existantes."""
        # Récupérer les colonnes actuelles de la table persons
        cursor = self.conn.execute("PRAGMA table_info(persons)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if not existing_cols:
            # Table vide ou inexistante → rien à migrer
            return

        changed = False

        # Migration 1 : classe → groupe (renommage)
        if "classe" in existing_cols and "groupe" not in existing_cols:
            try:
                self.conn.execute(
                    "ALTER TABLE persons RENAME COLUMN classe TO groupe"
                )
                changed = True
                logger.info("Migration: colonne 'classe' → 'groupe'")
            except sqlite3.OperationalError:
                # SQLite < 3.25 ne supporte pas RENAME COLUMN
                # Fallback : ajouter 'groupe', copier, supprimer 'classe' impossible
                # On ajoute 'groupe' et on copie les données
                self.conn.execute(
                    "ALTER TABLE persons ADD COLUMN groupe TEXT DEFAULT ''"
                )
                self.conn.execute(
                    "UPDATE persons SET groupe = classe"
                )
                changed = True
                logger.info(
                    "Migration (fallback): colonne 'groupe' ajoutée, "
                    "données copiées depuis 'classe'"
                )

        # Migration 2 : nouvelles colonnes
        new_columns = {
            "organisation": "TEXT DEFAULT ''",
            "notes":        "TEXT DEFAULT ''",
            "tags":         "TEXT DEFAULT ''",
            "metadata_json": "TEXT DEFAULT '{}'",
            "groupe":       "TEXT DEFAULT ''",   # au cas où ni classe ni groupe
        }
        # Re-lire les colonnes après migration 1
        cursor = self.conn.execute("PRAGMA table_info(persons)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_def in new_columns.items():
            if col_name not in existing_cols:
                try:
                    self.conn.execute(
                        f"ALTER TABLE persons ADD COLUMN {col_name} {col_def}"
                    )
                    changed = True
                    logger.info(f"Migration: colonne '{col_name}' ajoutée")
                except sqlite3.OperationalError:
                    pass  # colonne déjà existante (race condition)

        # Migration 3 : mettre à jour le rôle par défaut 'eleve' → 'visiteur'
        # seulement pour les personnes qui ont encore le rôle par défaut
        if "role" in existing_cols:
            updated = self.conn.execute(
                "UPDATE persons SET role = 'visiteur' "
                "WHERE role = 'eleve'"
            ).rowcount
            if updated > 0:
                changed = True
                logger.info(
                    f"Migration: {updated} personne(s) 'eleve' → 'visiteur'"
                )

        if changed:
            self.conn.commit()
            logger.info("Migrations de schéma appliquées avec succès")

    def _load_cache(self):
        """Charge toutes les personnes et embeddings en mémoire."""
        # Charger les personnes
        cursor = self.conn.execute(
            "SELECT * FROM persons WHERE actif = 1"
        )
        for row in cursor.fetchall():
            self._persons_cache[row["person_id"]] = dict(row)

        # Charger les embeddings
        cursor = self.conn.execute("SELECT person_id, embedding FROM embeddings")
        for row in cursor.fetchall():
            pid = row["person_id"]
            emb = pickle.loads(row["embedding"])
            if pid not in self._embeddings_cache:
                self._embeddings_cache[pid] = []
            self._embeddings_cache[pid].append(emb)

    # ─── CRUD Personnes ─────────────────────────────────────────

    def add_person(
        self,
        person_id: str,
        nom: str,
        prenom: str,
        groupe: str = "",
        role: str = "visiteur",
        organisation: str = "",
        date_naissance: str = "",
        email: str = "",
        telephone: str = "",
        heure_arrivee: str = "",
        heure_depart: str = "",
        photo_path: str = "",
        notes: str = "",
        tags: str = "",
        metadata: dict = None,
        # Backward compat alias
        classe: str = None,
    ) -> bool:
        """Ajoute une personne dans la base (universel)."""
        # Backward compat: 'classe' → 'groupe'
        if classe is not None and not groupe:
            groupe = classe

        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        try:
            self.conn.execute(
                """INSERT INTO persons
                   (person_id, nom, prenom, groupe, role, organisation,
                    date_naissance, email, telephone,
                    heure_arrivee_prevue, heure_depart_prevue,
                    photo_path, notes, tags, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (person_id, nom, prenom, groupe, role, organisation,
                 date_naissance, email, telephone,
                 heure_arrivee, heure_depart,
                 photo_path, notes, tags, metadata_json),
            )
            self.conn.commit()

            self._persons_cache[person_id] = {
                "person_id": person_id,
                "nom": nom,
                "prenom": prenom,
                "groupe": groupe,
                "role": role,
                "organisation": organisation,
                "heure_arrivee_prevue": heure_arrivee,
                "heure_depart_prevue": heure_depart,
                "notes": notes,
                "tags": tags,
            }

            label = f"{prenom} {nom}"
            if groupe:
                label += f" ({groupe})"
            if organisation:
                label += f" [{organisation}]"
            logger.info(f"  👤 Ajouté : {label} — rôle: {role}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"  ⚠️ Personne déjà existante : {person_id}")
            return False

    def add_embedding(
        self,
        person_id: str,
        embedding: np.ndarray,
        source: str = "enrollment",
    ) -> bool:
        """Ajoute un embedding facial pour une personne."""
        if person_id not in self._persons_cache:
            logger.warning(f"  ⚠️ Personne inconnue : {person_id}")
            return False

        blob = pickle.dumps(embedding.astype(np.float32))
        self.conn.execute(
            "INSERT INTO embeddings (person_id, embedding, source) VALUES (?, ?, ?)",
            (person_id, blob, source),
        )
        self.conn.commit()

        if person_id not in self._embeddings_cache:
            self._embeddings_cache[person_id] = []
        self._embeddings_cache[person_id].append(embedding.astype(np.float32))

        n = len(self._embeddings_cache[person_id])
        logger.info(f"  🔢 Embedding ajouté pour {person_id} ({n} au total)")
        return True

    def get_person(self, person_id: str) -> Optional[Dict]:
        """Récupère les infos d'une personne."""
        return self._persons_cache.get(person_id)

    def get_all_persons(self) -> List[Dict]:
        """Liste toutes les personnes actives."""
        return list(self._persons_cache.values())

    def get_all_embeddings(self) -> Dict[str, List[np.ndarray]]:
        """Retourne tous les embeddings indexés par person_id."""
        return dict(self._embeddings_cache)

    def update_person(self, person_id: str, **kwargs) -> bool:
        """Met à jour les infos d'une personne."""
        # Backward compat: 'classe' → 'groupe'
        if "classe" in kwargs and "groupe" not in kwargs:
            kwargs["groupe"] = kwargs.pop("classe")
        elif "classe" in kwargs:
            kwargs.pop("classe")

        valid_fields = {
            "nom", "prenom", "groupe", "role", "organisation",
            "date_naissance", "email", "telephone",
            "heure_arrivee_prevue", "heure_depart_prevue",
            "photo_path", "notes", "tags", "metadata_json", "actif",
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [person_id]

        self.conn.execute(
            f"UPDATE persons SET {set_clause}, updated_at = datetime('now','localtime') WHERE person_id = ?",
            values,
        )
        self.conn.commit()

        # Mettre à jour le cache
        if person_id in self._persons_cache:
            self._persons_cache[person_id].update(updates)

        return True

    def delete_person(self, person_id: str) -> bool:
        """Désactive une personne (soft delete)."""
        return self.update_person(person_id, actif=0)

    # ─── Pointage (Attendance) ──────────────────────────────────

    def record_attendance(
        self,
        person_id: str,
        direction: str,
        similarity: float = 0.0,
        camera_id: str = "cam_01",
    ) -> Dict:
        """
        Enregistre un pointage (entrée ou sortie).

        Returns:
            Détails du pointage avec info de retard.
        """
        person = self._persons_cache.get(person_id, {})
        now = time.time()
        dt = datetime.fromtimestamp(now)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # Vérifier le retard
        is_late = False
        retard_min = 0.0

        if direction == "entry" and person:
            heure_prevue = person.get("heure_arrivee_prevue", "08:00")
            try:
                h, m = map(int, heure_prevue.split(":"))
                from datetime import time as dt_time
                prevue = dt.replace(hour=h, minute=m, second=0)
                if dt > prevue:
                    is_late = True
                    retard_min = (dt - prevue).total_seconds() / 60
            except (ValueError, AttributeError):
                pass

        self.conn.execute(
            """INSERT INTO attendance
               (person_id, nom, prenom, direction, timestamp, datetime_str,
                similarity, camera_id, is_late, retard_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                person_id,
                person.get("nom", ""),
                person.get("prenom", ""),
                direction, now, dt_str,
                similarity, camera_id,
                int(is_late), retard_min,
            ),
        )
        self.conn.commit()

        record = {
            "person_id": person_id,
            "nom": person.get("nom", ""),
            "prenom": person.get("prenom", ""),
            "classe": person.get("classe", ""),
            "direction": direction,
            "datetime": dt_str,
            "is_late": is_late,
            "retard_minutes": round(retard_min, 1),
            "similarity": round(similarity, 3),
        }

        if is_late:
            logger.warning(
                f"  ⏰ RETARD : {person.get('prenom', '')} {person.get('nom', '')} "
                f"({person.get('classe', '')}) — {retard_min:.0f} min de retard"
            )
        else:
            logger.info(
                f"  ✅ {direction.upper()} : {person.get('prenom', '')} "
                f"{person.get('nom', '')} ({person.get('classe', '')}) à {dt_str}"
            )

        return record

    def get_attendance_today(self, person_id: Optional[str] = None) -> List[Dict]:
        """Pointages du jour pour une personne ou toutes."""
        today = datetime.now().strftime("%Y-%m-%d")
        if person_id:
            cursor = self.conn.execute(
                "SELECT * FROM attendance WHERE person_id = ? AND datetime_str LIKE ?",
                (person_id, f"{today}%"),
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM attendance WHERE datetime_str LIKE ?",
                (f"{today}%",),
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_late_today(self) -> List[Dict]:
        """Liste les retards du jour."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.execute(
            "SELECT * FROM attendance WHERE is_late = 1 AND datetime_str LIKE ? ORDER BY retard_minutes DESC",
            (f"{today}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_absent_today(self) -> List[Dict]:
        """Liste les personnes absentes (pas de pointage aujourd'hui)."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.execute(
            """SELECT p.* FROM persons p
               WHERE p.actif = 1
               AND p.person_id NOT IN (
                   SELECT DISTINCT a.person_id FROM attendance a
                   WHERE a.datetime_str LIKE ? AND a.direction = 'entry'
               )""",
            (f"{today}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_attendance_stats(
        self, date_from: str = None, date_to: str = None
    ) -> Dict:
        """Statistiques de pointage sur une période."""
        today = datetime.now().strftime("%Y-%m-%d")
        date_from = date_from or today
        date_to = date_to or today

        cursor = self.conn.execute(
            """SELECT COUNT(DISTINCT person_id) as total_present,
                      SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) as total_retards,
                      AVG(CASE WHEN is_late = 1 THEN retard_minutes ELSE NULL END) as avg_retard,
                      MAX(retard_minutes) as max_retard
               FROM attendance
               WHERE direction = 'entry'
               AND datetime_str >= ? AND datetime_str <= ?""",
            (date_from, date_to + " 23:59:59"),
        )
        row = cursor.fetchone()

        total_inscrits = len(self._persons_cache)

        return {
            "date_from": date_from,
            "date_to": date_to,
            "total_inscrits": total_inscrits,
            "total_present": row["total_present"] or 0,
            "total_absent": total_inscrits - (row["total_present"] or 0),
            "total_retards": row["total_retards"] or 0,
            "retard_moyen_min": round(row["avg_retard"] or 0, 1),
            "retard_max_min": round(row["max_retard"] or 0, 1),
            "taux_presence": round(
                (row["total_present"] or 0) / max(total_inscrits, 1) * 100, 1
            ),
        }

    def close(self):
        """Ferme la connexion."""
        self.conn.close()


# ═══════════════════════════════════════════════════════════════
# 2. MOTEUR DE RECONNAISSANCE FACIALE (InsightFace Buffalo)
# ═══════════════════════════════════════════════════════════════

class FaceRecognizer:
    """
    Reconnaissance faciale basée sur InsightFace Buffalo_l.

    Pipeline :
    1. Détection de visages (RetinaFace)
    2. Alignement (5 landmarks)
    3. Extraction d'embeddings (ArcFace 512D)
    4. Matching contre la base de visages connus

    Le modèle Buffalo_l offre :
    - Détection : RetinaFace R50
    - Reconnaissance : ArcFace R100 (LResNet100E-IR)
    - Attributs : âge, genre
    """

    def __init__(
        self,
        face_db: FaceDatabase,
        model_name: str = "buffalo_l",
        det_size: Tuple[int, int] = (640, 640),
        similarity_threshold: float = 0.45,
        min_face_size: int = 30,
    ):
        """
        Args:
            face_db: Base de données des visages.
            model_name: Modèle InsightFace (buffalo_l, buffalo_s, buffalo_sc).
            det_size: Taille de détection.
            similarity_threshold: Seuil de similarité cosinus (0.4-0.6).
            min_face_size: Taille minimale du visage en pixels.
        """
        try:
            from insightface.app import FaceAnalysis
        except ImportError:
            raise ImportError(
                "insightface non installé ! "
                "Installer avec : pip install insightface onnxruntime-gpu"
            )

        self.face_db = face_db
        self.similarity_threshold = similarity_threshold
        self.min_face_size = min_face_size

        # Initialiser InsightFace
        self.app = FaceAnalysis(
            name=model_name,
            root=os.path.expanduser("~/.insightface"),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=0, det_size=det_size)

        # Pré-calculer les moyennes d'embeddings par personne
        self._known_embeddings: Dict[str, np.ndarray] = {}
        self._build_embedding_index()

        logger.info(
            f"✅ FaceRecognizer initialisé | "
            f"Modèle: {model_name} | "
            f"Seuil: {similarity_threshold} | "
            f"{len(self._known_embeddings)} visage(s) connu(s)"
        )

    def _build_embedding_index(self):
        """Construit l'index des embeddings moyens par personne."""
        all_embeddings = self.face_db.get_all_embeddings()
        self._known_embeddings.clear()

        for person_id, embs in all_embeddings.items():
            if embs:
                # Moyenne des embeddings (plus robuste)
                mean_emb = np.mean(embs, axis=0)
                # Normaliser L2
                mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-8)
                self._known_embeddings[person_id] = mean_emb

    def detect_faces(self, frame: np.ndarray) -> List[FaceInfo]:
        """
        Détecte tous les visages dans une frame.

        Returns:
            Liste de FaceInfo avec bbox, embedding, landmarks.
        """
        faces = self.app.get(frame)
        results = []

        for face in faces:
            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox

            # Filtrer les trop petits visages
            w, h = x2 - x1, y2 - y1
            if w < self.min_face_size or h < self.min_face_size:
                continue

            face_info = FaceInfo(
                bbox=(int(x1), int(y1), int(x2), int(y2)),
                embedding=face.embedding,
                confidence=float(face.det_score),
                landmarks=face.kps if hasattr(face, 'kps') else None,
                age=int(face.age) if hasattr(face, 'age') else None,
                gender='M' if hasattr(face, 'gender') and face.gender == 1 else 'F',
            )
            results.append(face_info)

        return results

    def identify(
        self,
        face: FaceInfo,
    ) -> Optional[IdentifiedPerson]:
        """
        Identifie un visage en le comparant à la base de données.

        Args:
            face: Informations du visage détecté.

        Returns:
            IdentifiedPerson si reconnu, None sinon.
        """
        if not self._known_embeddings:
            return None

        # Normaliser l'embedding
        query = face.embedding.astype(np.float32)
        query = query / (np.linalg.norm(query) + 1e-8)

        # Calculer la similarité cosinus avec tous les visages connus
        best_id = None
        best_sim = -1.0

        for person_id, known_emb in self._known_embeddings.items():
            sim = float(np.dot(query, known_emb))
            if sim > best_sim:
                best_sim = sim
                best_id = person_id

        # Vérifier le seuil
        if best_sim >= self.similarity_threshold and best_id is not None:
            person = self.face_db.get_person(best_id)
            if person:
                return IdentifiedPerson(
                    person_id=best_id,
                    nom=person.get("nom", ""),
                    prenom=person.get("prenom", ""),
                    groupe=person.get("groupe", person.get("classe", "")),
                    role=person.get("role", "visiteur"),
                    organisation=person.get("organisation", ""),
                    photo_path=person.get("photo_path", ""),
                    similarity=best_sim,
                    face_bbox=face.bbox,
                )

        return None

    def identify_all(
        self,
        frame: np.ndarray,
    ) -> Tuple[List[IdentifiedPerson], List[FaceInfo]]:
        """
        Détecte et identifie tous les visages dans une frame.

        Returns:
            (identifiés, inconnus) — deux listes séparées.
        """
        faces = self.detect_faces(frame)
        identified = []
        unknown = []

        for face in faces:
            person = self.identify(face)
            if person:
                identified.append(person)
            else:
                unknown.append(face)

        return identified, unknown

    def enroll_from_frame(
        self,
        frame: np.ndarray,
        person_id: str,
        nom: str,
        prenom: str,
        groupe: str = "",
        role: str = "visiteur",
        organisation: str = "",
        **kwargs,
    ) -> bool:
        """
        Enrôle une personne à partir d'une frame (photo).

        La frame doit contenir exactement un visage.

        Returns:
            True si l'enrôlement a réussi.
        """
        faces = self.detect_faces(frame)

        if len(faces) == 0:
            logger.error("  ❌ Aucun visage détecté dans l'image")
            return False
        if len(faces) > 1:
            logger.warning(
                f"  ⚠️ {len(faces)} visages détectés, utilisation du plus grand"
            )
            # Prendre le plus grand visage
            faces.sort(key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]), reverse=True)

        face = faces[0]

        # Ajouter la personne si elle n'existe pas
        self.face_db.add_person(
            person_id=person_id,
            nom=nom,
            prenom=prenom,
            groupe=groupe,
            role=role,
            organisation=organisation,
            **kwargs,
        )

        # Ajouter l'embedding
        success = self.face_db.add_embedding(
            person_id=person_id,
            embedding=face.embedding,
            source="enrollment",
        )

        if success:
            # Reconstruire l'index
            self._build_embedding_index()
            logger.info(
                f"  ✅ Enrôlé : {prenom} {nom}"
                f"{f' ({groupe})' if groupe else ''} "
                f"[conf: {face.confidence:.3f}]"
            )

        return success

    def enroll_from_image(
        self,
        image_path: str,
        person_id: str,
        nom: str,
        prenom: str,
        **kwargs,
    ) -> bool:
        """Enrôle une personne à partir d'un fichier image."""
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"  ❌ Image non trouvée : {image_path}")
            return False

        return self.enroll_from_frame(
            frame=img,
            person_id=person_id,
            nom=nom,
            prenom=prenom,
            photo_path=image_path,
            **kwargs,
        )

    def enroll_from_directory(
        self,
        directory: str,
        groupe: str = "",
        role: str = "visiteur",
        organisation: str = "",
    ) -> int:
        """
        Enrôle toutes les personnes depuis un dossier.

        Structure attendue :
            directory/
            ├── NOM_Prenom_ID/
            │   ├── photo1.jpg
            │   ├── photo2.jpg
            │   └── ...
            ├── DUPONT_Jean_001/
            │   └── photo.jpg
            └── ...

        Chaque sous-dossier est nommé : NOM_Prenom_ID

        Returns:
            Nombre de personnes enrôlées.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.error(f"  ❌ Dossier non trouvé : {directory}")
            return 0

        enrolled = 0

        for person_dir in sorted(dir_path.iterdir()):
            if not person_dir.is_dir():
                continue

            # Parser le nom du dossier : NOM_Prenom_ID
            parts = person_dir.name.split("_")
            if len(parts) >= 3:
                nom = parts[0]
                prenom = parts[1]
                person_id = parts[2]
            elif len(parts) == 2:
                nom = parts[0]
                prenom = parts[1]
                person_id = f"{nom}_{prenom}".lower()
            else:
                nom = person_dir.name
                prenom = ""
                person_id = nom.lower()

            # Ajouter la personne
            self.face_db.add_person(
                person_id=person_id,
                nom=nom,
                prenom=prenom,
                groupe=groupe,
                role=role,
                organisation=organisation,
            )

            # Enrôler chaque photo
            photos = list(person_dir.glob("*.jpg")) + \
                     list(person_dir.glob("*.jpeg")) + \
                     list(person_dir.glob("*.png"))

            for photo in photos:
                img = cv2.imread(str(photo))
                if img is None:
                    continue

                faces = self.detect_faces(img)
                if faces:
                    # Plus grand visage
                    faces.sort(
                        key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]),
                        reverse=True,
                    )
                    self.face_db.add_embedding(
                        person_id=person_id,
                        embedding=faces[0].embedding,
                        source=f"photo:{photo.name}",
                    )

            enrolled += 1
            logger.info(
                f"  📸 {prenom} {nom} enrôlé ({len(photos)} photo(s))"
            )

        # Reconstruire l'index
        self._build_embedding_index()
        logger.info(f"\n✅ {enrolled} personne(s) enrôlée(s) depuis {directory}")
        return enrolled

    def add_embedding_for_track(
        self,
        person_id: str,
        face: FaceInfo,
    ) -> bool:
        """
        Ajoute un embedding supplémentaire capturé en temps réel
        pour améliorer la reconnaissance.
        """
        success = self.face_db.add_embedding(
            person_id=person_id,
            embedding=face.embedding,
            source="realtime",
        )
        if success:
            self._build_embedding_index()
        return success

    def draw_identifications(
        self,
        frame: np.ndarray,
        identified: List[IdentifiedPerson],
        unknown: List[FaceInfo],
    ) -> np.ndarray:
        """Dessine les identifications sur la frame."""
        annotated = frame.copy()

        # Visages identifiés (vert)
        for person in identified:
            x1, y1, x2, y2 = person.face_bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Label contextuel
            label = f"{person.display_label} {person.similarity:.0%}"

            # Background du label
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
            )
            cv2.rectangle(
                annotated,
                (x1, y1 - th - 10), (x1 + tw + 5, y1),
                (0, 255, 0), -1,
            )
            cv2.putText(
                annotated, label,
                (x1 + 2, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 0), 2,
            )

        # Visages inconnus (rouge)
        for face in unknown:
            x1, y1, x2, y2 = face.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)

            label = f"Inconnu {face.confidence:.0%}"
            cv2.putText(
                annotated, label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 0, 255), 2,
            )

        return annotated

    def refresh_index(self):
        """Recharge l'index des embeddings depuis la base."""
        self.face_db._load_cache()
        self._build_embedding_index()
        logger.info(
            f"🔄 Index rechargé : {len(self._known_embeddings)} visage(s)"
        )
