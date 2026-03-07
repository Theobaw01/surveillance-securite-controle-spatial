"""
═══════════════════════════════════════════════════════════════
MODULE 10 — Gestionnaire Universel de Personnes
═══════════════════════════════════════════════════════════════
- Gestion universelle : entreprises, écoles, événements, bâtiments
- Inscription / modification / suppression
- Suivi de présence avec pointage automatique
- Rapports de présence (journalier, par groupe, par personne)
- Alertes en temps réel (retard, absence, temps prolongé)
- Export CSV / JSON des rapports
- Compatible avec n'importe quel contexte d'utilisation
═══════════════════════════════════════════════════════════════
"""

import os
import csv
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PROFILS PRÉ-DÉFINIS (templates de configuration)
# ═══════════════════════════════════════════════════════════════

PROFILS = {
    "ecole": {
        "nom": "Établissement Scolaire",
        "roles": ["eleve", "professeur", "personnel", "directeur"],
        "groupe_label": "Classe",
        "horaires": {
            "lundi":    {"debut": "08:00", "fin": "17:00"},
            "mardi":    {"debut": "08:00", "fin": "17:00"},
            "mercredi": {"debut": "08:00", "fin": "12:00"},
            "jeudi":    {"debut": "08:00", "fin": "17:00"},
            "vendredi": {"debut": "08:00", "fin": "17:00"},
        },
        "tolerance_minutes": 5,
    },
    "entreprise": {
        "nom": "Entreprise",
        "roles": ["employe", "manager", "directeur", "visiteur", "stagiaire"],
        "groupe_label": "Département",
        "horaires": {
            "lundi":    {"debut": "09:00", "fin": "18:00"},
            "mardi":    {"debut": "09:00", "fin": "18:00"},
            "mercredi": {"debut": "09:00", "fin": "18:00"},
            "jeudi":    {"debut": "09:00", "fin": "18:00"},
            "vendredi": {"debut": "09:00", "fin": "18:00"},
        },
        "tolerance_minutes": 10,
    },
    "evenement": {
        "nom": "Événement",
        "roles": ["participant", "staff", "vip", "presse", "organisateur"],
        "groupe_label": "Catégorie",
        "horaires": {},
        "tolerance_minutes": 0,
    },
    "batiment": {
        "nom": "Bâtiment / Résidence",
        "roles": ["resident", "visiteur", "livreur", "personnel", "gardien"],
        "groupe_label": "Étage / Zone",
        "horaires": {},
        "tolerance_minutes": 0,
    },
    "libre": {
        "nom": "Configuration Libre",
        "roles": ["personne"],
        "groupe_label": "Groupe",
        "horaires": {},
        "tolerance_minutes": 0,
    },
}


# ═══════════════════════════════════════════════════════════════
# GESTIONNAIRE UNIVERSEL DE PERSONNES
# ═══════════════════════════════════════════════════════════════

class PersonManager:
    """
    Gestionnaire universel de personnes pour tout contexte.

    Utilisable pour :
    - Écoles : pointage des élèves, retards, absences par classe
    - Entreprises : entrées/sorties des employés, visiteurs
    - Événements : accès VIP, comptage participants, staff
    - Bâtiments : résidents, visiteurs, livreurs
    - Tout autre contexte avec reconnaissance faciale

    Fonctionnalités :
    - Enregistrer / modifier / supprimer des personnes
    - Vérifier les retards (si horaires définis)
    - Générer des rapports de présence
    - Alertes pour responsables
    - Statistiques par groupe, par personne, par période
    """

    def __init__(
        self,
        face_db,
        profil: str = "libre",
        organisation: str = "",
    ):
        """
        Args:
            face_db: Instance de FaceDatabase.
            profil: Profil de configuration ("ecole", "entreprise", "evenement", "batiment", "libre").
            organisation: Nom de l'organisation.
        """
        self.face_db = face_db
        self.organisation = organisation

        # Charger le profil
        config = PROFILS.get(profil, PROFILS["libre"])
        self.profil_nom = config["nom"]
        self.roles_disponibles = config["roles"]
        self.groupe_label = config["groupe_label"]
        self.horaires = dict(config.get("horaires", {}))
        self.tolerance_minutes = config.get("tolerance_minutes", 0)

        logger.info(
            f"✅ PersonManager initialisé | "
            f"Profil: {self.profil_nom} | "
            f"Organisation: {organisation or '(libre)'}"
        )

    # ─── Configuration ──────────────────────────────────────────

    def set_schedule(
        self,
        jour: str,
        heure_debut: str = "08:00",
        heure_fin: str = "17:00",
    ):
        """Configure les horaires pour un jour donné."""
        self.horaires[jour.lower()] = {
            "debut": heure_debut,
            "fin": heure_fin,
        }

    def set_tolerance(self, minutes: int = 5):
        """Configure la marge de tolérance pour les retards."""
        self.tolerance_minutes = minutes

    # ─── Inscription ────────────────────────────────────────────

    def inscrire(
        self,
        person_id: str,
        nom: str,
        prenom: str,
        groupe: str = "",
        role: str = "",
        organisation: str = "",
        email: str = "",
        telephone: str = "",
        heure_arrivee: str = "",
        heure_depart: str = "",
        notes: str = "",
        tags: str = "",
        metadata: dict = None,
        # Backward compat
        classe: str = None,
    ) -> bool:
        """
        Inscrit une personne (universel).

        Args:
            person_id: Identifiant unique.
            nom: Nom de famille.
            prenom: Prénom.
            groupe: Classe, département, catégorie...
            role: Rôle de la personne.
            organisation: Organisation d'appartenance.
            email: Email (optionnel).
            telephone: Téléphone (optionnel).
            heure_arrivee: Heure d'arrivée prévue.
            heure_depart: Heure de départ prévue.
            notes: Notes libres.
            tags: Tags séparés par virgule.
            metadata: Dictionnaire de métadonnées libres.
        """
        # Backward compat
        if classe is not None and not groupe:
            groupe = classe

        if not role:
            role = self.roles_disponibles[0] if self.roles_disponibles else "personne"

        if not organisation:
            organisation = self.organisation

        return self.face_db.add_person(
            person_id=person_id,
            nom=nom,
            prenom=prenom,
            groupe=groupe,
            role=role,
            organisation=organisation,
            email=email,
            telephone=telephone,
            heure_arrivee=heure_arrivee,
            heure_depart=heure_depart,
            notes=notes,
            tags=tags,
            metadata=metadata,
        )

    def modifier(self, person_id: str, **kwargs) -> bool:
        """Modifie les informations d'une personne."""
        return self.face_db.update_person(person_id, **kwargs)

    def supprimer(self, person_id: str) -> bool:
        """Désactive une personne (soft delete)."""
        return self.face_db.delete_person(person_id)

    def lister(
        self,
        groupe: Optional[str] = None,
        role: Optional[str] = None,
        organisation: Optional[str] = None,
    ) -> List[Dict]:
        """
        Liste les personnes actives avec filtres optionnels.

        Args:
            groupe: Filtrer par groupe (classe, département...).
            role: Filtrer par rôle.
            organisation: Filtrer par organisation.
        """
        persons = self.face_db.get_all_persons()

        if groupe:
            persons = [p for p in persons if p.get("groupe") == groupe]
        if role:
            persons = [p for p in persons if p.get("role") == role]
        if organisation:
            persons = [p for p in persons if p.get("organisation") == organisation]

        return sorted(
            persons,
            key=lambda p: (p.get("groupe", ""), p.get("nom", "")),
        )

    def lister_groupes(self) -> List[str]:
        """Liste tous les groupes distincts."""
        persons = self.face_db.get_all_persons()
        groupes = set()
        for p in persons:
            g = p.get("groupe", "")
            if g:
                groupes.add(g)
        return sorted(groupes)

    def get_info(self, person_id: str) -> Optional[Dict]:
        """Récupère les informations complètes d'une personne."""
        return self.face_db.get_person(person_id)

    def compter(
        self,
        groupe: Optional[str] = None,
        role: Optional[str] = None,
    ) -> int:
        """Compte le nombre de personnes inscrites."""
        return len(self.lister(groupe=groupe, role=role))

    # ─── Vérification des retards ───────────────────────────────

    def verifier_retard(
        self,
        person_id: str,
        heure_entree: datetime,
    ) -> Dict:
        """
        Vérifie si une personne est en retard.

        Returns:
            {
                "is_late": bool,
                "retard_minutes": float,
                "heure_prevue": str,
                "heure_arrivee": str,
                "dans_tolerance": bool,
            }
        """
        person = self.face_db.get_person(person_id)
        if not person:
            return {"is_late": False, "retard_minutes": 0}

        heure_prevue_str = person.get("heure_arrivee_prevue", "")
        if not heure_prevue_str:
            return {"is_late": False, "retard_minutes": 0}

        # Vérifier le jour
        jours = {
            0: "lundi", 1: "mardi", 2: "mercredi",
            3: "jeudi", 4: "vendredi", 5: "samedi", 6: "dimanche",
        }
        jour = jours.get(heure_entree.weekday(), "")
        if jour in self.horaires:
            heure_prevue_str = self.horaires[jour]["debut"]
        elif not heure_prevue_str:
            return {"is_late": False, "retard_minutes": 0}

        try:
            h, m = map(int, heure_prevue_str.split(":"))
            heure_prevue = heure_entree.replace(
                hour=h, minute=m, second=0, microsecond=0
            )
        except (ValueError, AttributeError):
            return {"is_late": False, "retard_minutes": 0}

        retard_min = (heure_entree - heure_prevue).total_seconds() / 60
        is_late = retard_min > self.tolerance_minutes

        return {
            "is_late": is_late,
            "retard_minutes": round(max(0, retard_min), 1),
            "heure_prevue": heure_prevue_str,
            "heure_arrivee": heure_entree.strftime("%H:%M:%S"),
            "dans_tolerance": 0 < retard_min <= self.tolerance_minutes,
        }

    # ─── Rapports ───────────────────────────────────────────────

    def rapport_journalier(self, date: Optional[str] = None) -> Dict:
        """
        Génère le rapport de présence du jour.

        Returns:
            {
                "date": str,
                "profil": str,
                "organisation": str,
                "total_inscrits": int,
                "total_presents": int,
                "total_absents": int,
                "total_retards": int,
                "retard_moyen_min": float,
                "taux_presence": float,
                "par_groupe": {...},
                "retardataires": [...],
                "absents": [...],
            }
        """
        date = date or datetime.now().strftime("%Y-%m-%d")

        # Toutes les personnes
        personnes = self.lister()
        total_inscrits = len(personnes)

        # Pointages du jour
        pointages = self.face_db.get_attendance_today()

        # Personnes présentes (au moins une entrée)
        present_ids = set()
        for p in pointages:
            if p.get("direction") == "entry":
                present_ids.add(p["person_id"])

        # Retards du jour
        retards = self.face_db.get_late_today()
        retards_ids = {r["person_id"] for r in retards}

        # Absents
        absents = [
            p for p in personnes
            if p["person_id"] not in present_ids
        ]

        # Retardataires avec détails
        retardataires = []
        for r in retards:
            person = self.face_db.get_person(r["person_id"])
            if person:
                retardataires.append({
                    "person_id": r["person_id"],
                    "nom": person.get("nom", ""),
                    "prenom": person.get("prenom", ""),
                    "groupe": person.get("groupe", ""),
                    "role": person.get("role", ""),
                    "heure_arrivee": r.get("datetime_str", ""),
                    "retard_minutes": r.get("retard_minutes", 0),
                })

        # Stats par groupe
        par_groupe = defaultdict(lambda: {
            "inscrits": 0, "presents": 0, "absents": 0,
            "retards": 0, "taux_presence": 0,
        })

        for p in personnes:
            grp = p.get("groupe", "Sans groupe")
            par_groupe[grp]["inscrits"] += 1
            if p["person_id"] in present_ids:
                par_groupe[grp]["presents"] += 1
            else:
                par_groupe[grp]["absents"] += 1
            if p["person_id"] in retards_ids:
                par_groupe[grp]["retards"] += 1

        for grp, stats in par_groupe.items():
            total = stats["inscrits"]
            stats["taux_presence"] = round(
                stats["presents"] / max(total, 1) * 100, 1
            )

        # Retard moyen
        retard_minutes = [r.get("retard_minutes", 0) for r in retards]
        retard_moyen = (
            round(sum(retard_minutes) / len(retard_minutes), 1)
            if retard_minutes else 0
        )

        return {
            "date": date,
            "profil": self.profil_nom,
            "organisation": self.organisation,
            "groupe_label": self.groupe_label,
            "total_inscrits": total_inscrits,
            "total_presents": len(present_ids),
            "total_absents": len(absents),
            "total_retards": len(retards),
            "retard_moyen_min": retard_moyen,
            "taux_presence": round(
                len(present_ids) / max(total_inscrits, 1) * 100, 1
            ),
            "par_groupe": dict(par_groupe),
            "retardataires": retardataires,
            "absents": [
                {
                    "person_id": a["person_id"],
                    "nom": a.get("nom", ""),
                    "prenom": a.get("prenom", ""),
                    "groupe": a.get("groupe", ""),
                    "role": a.get("role", ""),
                }
                for a in absents
            ],
        }

    def rapport_personne(
        self,
        person_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict:
        """
        Rapport individuel d'une personne sur une période.

        Returns:
            Historique de présence, retards, statistiques.
        """
        person = self.face_db.get_person(person_id)
        if not person:
            return {"error": f"Personne non trouvée : {person_id}"}

        date_from = date_from or datetime.now().strftime("%Y-%m-%d")
        date_to = date_to or date_from

        cursor = self.face_db.conn.execute(
            """SELECT * FROM attendance
               WHERE person_id = ?
               AND datetime_str >= ? AND datetime_str <= ?
               ORDER BY datetime_str""",
            (person_id, date_from, date_to + " 23:59:59"),
        )
        records = [dict(row) for row in cursor.fetchall()]

        total_jours = len(set(
            r["datetime_str"][:10] for r in records if r["direction"] == "entry"
        ))
        total_retards = sum(1 for r in records if r.get("is_late"))
        retard_total_min = sum(
            r.get("retard_minutes", 0) for r in records if r.get("is_late")
        )

        return {
            "person_id": person_id,
            "nom": person.get("nom", ""),
            "prenom": person.get("prenom", ""),
            "groupe": person.get("groupe", ""),
            "role": person.get("role", ""),
            "organisation": person.get("organisation", ""),
            "periode": f"{date_from} → {date_to}",
            "total_jours_present": total_jours,
            "total_retards": total_retards,
            "retard_cumule_min": round(retard_total_min, 1),
            "retard_moyen_min": round(
                retard_total_min / max(total_retards, 1), 1
            ),
            "historique": records,
        }

    def rapport_groupe(
        self,
        groupe: str,
        date: Optional[str] = None,
    ) -> Dict:
        """Rapport de présence par groupe."""
        personnes = self.lister(groupe=groupe)
        date = date or datetime.now().strftime("%Y-%m-%d")

        rapport_personnes = []
        total_present = 0
        total_retard = 0

        for p in personnes:
            pointage = self.face_db.conn.execute(
                """SELECT * FROM attendance
                   WHERE person_id = ?
                   AND datetime_str LIKE ?
                   AND direction = 'entry'
                   ORDER BY datetime_str LIMIT 1""",
                (p["person_id"], f"{date}%"),
            ).fetchone()

            est_present = pointage is not None
            est_retard = False
            retard_min = 0

            if pointage:
                total_present += 1
                est_retard = bool(pointage["is_late"])
                retard_min = pointage["retard_minutes"]
                if est_retard:
                    total_retard += 1

            rapport_personnes.append({
                "person_id": p["person_id"],
                "nom": p.get("nom", ""),
                "prenom": p.get("prenom", ""),
                "role": p.get("role", ""),
                "present": est_present,
                "en_retard": est_retard,
                "retard_minutes": retard_min,
                "heure_arrivee": dict(pointage).get("datetime_str", "-") if pointage else "-",
            })

        return {
            "groupe": groupe,
            "groupe_label": self.groupe_label,
            "date": date,
            "total_inscrits": len(personnes),
            "total_presents": total_present,
            "total_absents": len(personnes) - total_present,
            "total_retards": total_retard,
            "taux_presence": round(
                total_present / max(len(personnes), 1) * 100, 1
            ),
            "personnes": rapport_personnes,
        }

    # ─── Export ─────────────────────────────────────────────────

    def export_csv(
        self,
        rapport: Dict,
        output_path: str = "outputs/rapport_presence.csv",
    ) -> str:
        """Exporte un rapport journalier en CSV."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(["RAPPORT DE PRÉSENCE"])
            writer.writerow(["Profil", rapport.get("profil", "")])
            writer.writerow(["Organisation", rapport.get("organisation", "")])
            writer.writerow(["Date", rapport.get("date", "")])
            writer.writerow([
                "Inscrits", rapport.get("total_inscrits", 0),
                "Présents", rapport.get("total_presents", 0),
                "Absents", rapport.get("total_absents", 0),
                "Retards", rapport.get("total_retards", 0),
            ])
            writer.writerow([
                "Taux de présence", f"{rapport.get('taux_presence', 0)}%",
            ])
            writer.writerow([])

            # Retardataires
            if rapport.get("retardataires"):
                writer.writerow(["RETARDATAIRES"])
                writer.writerow([
                    "Nom", "Prénom", rapport.get("groupe_label", "Groupe"),
                    "Rôle", "Heure arrivée", "Retard (min)",
                ])
                for r in rapport["retardataires"]:
                    writer.writerow([
                        r.get("nom", ""), r.get("prenom", ""),
                        r.get("groupe", ""), r.get("role", ""),
                        r.get("heure_arrivee", ""),
                        r.get("retard_minutes", 0),
                    ])
                writer.writerow([])

            # Absents
            if rapport.get("absents"):
                writer.writerow(["ABSENTS"])
                writer.writerow([
                    "Nom", "Prénom", rapport.get("groupe_label", "Groupe"), "Rôle",
                ])
                for a in rapport["absents"]:
                    writer.writerow([
                        a.get("nom", ""), a.get("prenom", ""),
                        a.get("groupe", ""), a.get("role", ""),
                    ])
                writer.writerow([])

            # Par groupe
            if rapport.get("par_groupe"):
                writer.writerow([f"PAR {rapport.get('groupe_label', 'GROUPE').upper()}"])
                writer.writerow([
                    rapport.get("groupe_label", "Groupe"),
                    "Inscrits", "Présents", "Absents", "Retards", "Taux (%)",
                ])
                for grp, stats in sorted(rapport.get("par_groupe", {}).items()):
                    writer.writerow([
                        grp, stats["inscrits"], stats["presents"],
                        stats["absents"], stats["retards"], stats["taux_presence"],
                    ])

        logger.info(f"📄 Rapport CSV exporté : {output_path}")
        return output_path

    def export_json(
        self,
        rapport: Dict,
        output_path: str = "outputs/rapport_presence.json",
    ) -> str:
        """Exporte un rapport en JSON."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rapport, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"📄 Rapport JSON exporté : {output_path}")
        return output_path

    # ─── Affichage ──────────────────────────────────────────────

    def afficher_rapport(self, date: Optional[str] = None):
        """Affiche le rapport journalier dans le terminal."""
        rapport = self.rapport_journalier(date)
        grp_label = rapport.get("groupe_label", "Groupe")

        print(f"\n{'='*65}")
        print(f"  {'RAPPORT DE PRÉSENCE':^61}")
        print(f"{'='*65}")
        print(f"  Profil        : {rapport['profil']}")
        print(f"  Organisation  : {rapport['organisation'] or '—'}")
        print(f"  Date          : {rapport['date']}")
        print(f"  Inscrits      : {rapport['total_inscrits']}")
        print(f"  Présents      : {rapport['total_presents']}")
        print(f"  Absents       : {rapport['total_absents']}")
        print(f"  Retards       : {rapport['total_retards']}")
        print(f"  Retard moyen  : {rapport['retard_moyen_min']} min")
        print(f"  Taux présence : {rapport['taux_presence']}%")

        if rapport["retardataires"]:
            print(f"\n{'─'*65}")
            print(f"  ⏰ RETARDATAIRES ({len(rapport['retardataires'])})")
            print(f"{'─'*65}")
            for r in rapport["retardataires"]:
                base = f"  • {r['prenom']} {r['nom']}"
                if r.get("groupe"):
                    base += f" ({r['groupe']})"
                base += f" — arrivé à {r['heure_arrivee']} ({r['retard_minutes']}min)"
                print(base)

        if rapport["absents"]:
            print(f"\n{'─'*65}")
            print(f"  ❌ ABSENTS ({len(rapport['absents'])})")
            print(f"{'─'*65}")
            for a in rapport["absents"]:
                base = f"  • {a['prenom']} {a['nom']}"
                if a.get("groupe"):
                    base += f" ({a['groupe']})"
                print(base)

        if rapport["par_groupe"]:
            print(f"\n{'─'*65}")
            print(f"  📊 PAR {grp_label.upper()}")
            print(f"{'─'*65}")
            for grp, stats in sorted(rapport["par_groupe"].items()):
                print(
                    f"  {grp:15} | "
                    f"P:{stats['presents']}/{stats['inscrits']} "
                    f"| R:{stats['retards']} "
                    f"| {stats['taux_presence']}%"
                )

        print(f"{'='*65}\n")


# ═══════════════════════════════════════════════════════════════
# BACKWARD COMPAT — StudentManager wrapper
# ═══════════════════════════════════════════════════════════════

class StudentManager(PersonManager):
    """
    Gestionnaire scolaire — wrapper autour de PersonManager.
    Conservé pour la compatibilité avec le code existant.
    """

    def __init__(self, face_db, organisation: str = ""):
        super().__init__(
            face_db=face_db,
            profil="ecole",
            organisation=organisation,
        )

    def inscrire_eleve(
        self,
        person_id: str,
        nom: str,
        prenom: str,
        classe: str = "",
        **kwargs,
    ) -> bool:
        return self.inscrire(
            person_id=person_id, nom=nom, prenom=prenom,
            groupe=classe, role="eleve", **kwargs,
        )

    def inscrire_personnel(
        self,
        person_id: str,
        nom: str,
        prenom: str,
        role: str = "professeur",
        **kwargs,
    ) -> bool:
        return self.inscrire(
            person_id=person_id, nom=nom, prenom=prenom,
            role=role, **kwargs,
        )

    def lister_eleves(self, classe: Optional[str] = None) -> List[Dict]:
        return self.lister(groupe=classe, role="eleve")

    def lister_classes(self) -> List[str]:
        return self.lister_groupes()

    def modifier_eleve(self, person_id: str, **kwargs) -> bool:
        return self.modifier(person_id, **kwargs)

    def supprimer_eleve(self, person_id: str) -> bool:
        return self.supprimer(person_id)

    def rapport_journalier(self, date: Optional[str] = None) -> Dict:
        return super().rapport_journalier(date)

    def rapport_eleve(self, person_id: str, **kwargs) -> Dict:
        return self.rapport_personne(person_id, **kwargs)

    def rapport_classe(self, classe: str, date: Optional[str] = None) -> Dict:
        return self.rapport_groupe(classe, date)
