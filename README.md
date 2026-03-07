<div align="center">

# 🎥 Surveillance-IA

### Système universel de surveillance intelligente avec reconnaissance faciale

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![YOLO v8](https://img.shields.io/badge/YOLOv8L-Ultralytics-purple.svg)](https://docs.ultralytics.com)
[![InsightFace](https://img.shields.io/badge/InsightFace-Buffalo-orange.svg)](https://github.com/deepinsight/insightface)
[![FastAPI](https://img.shields.io/badge/FastAPI-WebSockets-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://docker.com)

*Détection, tracking, reconnaissance faciale et comptage de personnes en temps réel*
*Entreprises · Événements · Bâtiments · Établissements scolaires · Tout contexte*
*Projet SAHELYS*

---

<img src="docs/surveillance_demo.gif" alt="Surveillance-IA Demo" width="700">

</div>

---

## 🎯 Vue d'ensemble

**Surveillance-IA** est un système complet de surveillance intelligente qui analyse des flux vidéo en temps réel. Il détecte les personnes, les suit avec des IDs persistants, les **identifie par reconnaissance faciale**, et enregistre automatiquement leurs **entrées, sorties et temps de présence**.

Le système est **universel** et s'adapte à tout contexte professionnel :

| Secteur | Exemples d'utilisation |
|---------|------------------------|
| 🏢 **Entreprises** | Pointage employés, gestion visiteurs, contrôle d'accès, rapports RH |
| 🎪 **Événements** | Accréditation VIP/presse, comptage participants, sécurité |
| 🏠 **Bâtiments** | Accès résidents, suivi livreurs, gardiennage intelligent |
| 🏫 **Établissements scolaires** | Présence élèves, retards, rapports par classe |
| 🏭 **Industrie** | Zones sécurisées, temps de présence, alertes d'intrusion |
| 🏥 **Santé** | Suivi patients/visiteurs, contrôle d'accès zones |
| 💼 **Co-working** | Gestion des membres, occupation des espaces |

### Fonctionnalités principales

| Fonctionnalité | Description |
|----------------|-------------|
| 🔍 **Détection** | YOLO v8 Large fine-tuné sur COCO train2017 (~64k images personnes) |
| 🏃 **Tracking** | ByteTrack multi-personnes avec IDs persistants et trajectoires |
| 👤 **Reconnaissance faciale** | InsightFace Buffalo — identification par nom/prénom en temps réel |
| 📝 **Enregistrement** | Enregistrer des visages (photo, webcam, lot) et associer un nom |
| 🚪 **Entrées / Sorties** | Lignes virtuelles directionnelles, comptage IN/OUT automatique |
| ⏱️ **Temps de présence** | Chronomètre par personne, heure d'arrivée, heure de départ, durée |
| 📋 **Pointage automatique** | Personne reconnue → pointage enregistré avec direction + heure |
| ⏰ **Retards** | Détection automatique des retards (horaires configurables par profil) |
| 📊 **Rapports** | Journalier, par groupe, par personne — export CSV / JSON / PDF |
| 🌐 **API** | FastAPI + WebSockets, authentification JWT |
| 📈 **Dashboard** | Streamlit : flux vidéo, compteurs, histogrammes, identités |
| 🗄️ **Base de données** | SQLite (visages/pointages) + PostgreSQL (événements/stats) |
| 🐳 **Docker** | Multi-stage : API + Dashboard + GPU |

---

## 🔄 Pipeline de fonctionnement

```
 1. ENREGISTREMENT                    2. SURVEILLANCE TEMPS RÉEL
 ─────────────────                    ──────────────────────────

 ┌───────────────┐                    ┌───────────────┐
 │  📸 Photo     │                    │  📹 Caméra    │
 │  ou Webcam    │                    │  Flux vidéo   │
 └───────┬───────┘                    └───────┬───────┘
         │                                    │
         ▼                                    ▼
 ┌───────────────┐                    ┌───────────────┐
 │  InsightFace  │                    │  YOLO v8L     │
 │  Buffalo_l    │                    │  Détection    │
 │  Extraction   │                    └───────┬───────┘
 │  Embedding    │                            │
 └───────┬───────┘                            ▼
         │                            ┌───────────────┐
         ▼                            │  ByteTrack    │
 ┌───────────────┐                    │  Tracking     │
 │  SQLite DB    │◄──── Matching ────▶│  ID persistant│
 │  faces.db     │                    └───────┬───────┘
 │  - Nom        │                            │
 │  - Prénom     │                            ▼
 │  - Groupe     │                    ┌───────────────┐
 │  - Rôle       │                    │  InsightFace  │──── Reconnaissance
 │  - Embedding  │◄─────────────────▶│  Identification│     par visage
 └───────────────┘                    └───────┬───────┘
                                              │
                    ┌─────────────────────────┼──────────────────────┐
                    │                         │                      │
                    ▼                         ▼                      ▼
            ┌───────────────┐         ┌───────────────┐      ┌───────────────┐
            │  🚪 Compteur  │         │  ⏱️ Timer     │      │  📋 Pointage  │
            │  IN / OUT     │         │  Présence     │      │  Automatique  │
            │  Occupation   │         │  par personne │      │  Entrée/Sortie│
            └───────┬───────┘         └───────┬───────┘      │  Heure        │
                    │                         │              │  Retard       │
                    └────────────┬────────────┘              └───────┬───────┘
                                 │                                   │
                          ┌──────▼──────┐                    ┌───────▼───────┐
                          │  Overlay    │                    │  Rapports     │
                          │  Temps réel │                    │  CSV / JSON   │
                          │  Noms +     │                    │  PDF          │
                          │  Compteurs  │                    └───────────────┘
                          └─────────────┘
```

### Ce qui se passe après l'enregistrement d'une personne :

1. **Enregistrement** → Vous enregistrez le visage avec nom, prénom, groupe, rôle
2. **Détection** → YOLO détecte toutes les personnes dans le flux vidéo
3. **Tracking** → ByteTrack attribue un ID persistant à chaque personne
4. **Reconnaissance** → InsightFace compare le visage au registre → identifie la personne par son nom
5. **Comptage** → Quand la personne traverse une ligne virtuelle → entrée ou sortie enregistrée
6. **Pointage automatique** → Heure d'arrivée, heure de départ, direction, similarité → stockés en BDD
7. **Présence** → Chronomètre de présence par personne → durée totale calculée
8. **Retard** → Si horaires définis → vérification automatique du retard
9. **Overlay** → Le nom, le groupe et le % de similarité s'affichent en temps réel sur la vidéo
10. **Rapports** → Présences, absences, retards → exportables en CSV/JSON/PDF

---

## 📊 Performance

| Métrique | Objectif | Détails |
|----------|----------|---------|
| **Precision** | **≥96%** | Détection de personnes |
| Recall | ≥94% | |
| mAP@0.5 | ≥95% | |
| mAP@0.5:0.95 | ≥85% | |
| FPS (GPU T4) | ~35-45 FPS | Avec reconnaissance faciale |
| FPS (CPU) | ~5-8 FPS | |

### Entraînement (Notebook Colab optimisé)

| Paramètre | Valeur |
|-----------|--------|
| Modèle de base | **yolov8l.pt** (Large, 43.7M params) |
| Dataset | **COCO train2017** (~64k person images) |
| Epochs | **120** |
| Optimizer | **AdamW** (lr=0.001) |
| Batch size | **Auto** (max VRAM) |
| Image size | 640×640 |
| Augmentation | CopyPaste=0.3, Mixup=0.15, Mosaic, Erasing=0.1 |
| Close mosaic | 15 derniers epochs |
| Label smoothing | 0.01 |
| Early stopping | patience=20 |
| Validation | COCO val2017 (split 50/50 → val/test) |

---

## 📁 Structure du projet

```
surveillance/
├── src/
│   ├── __init__.py            # Package principal
│   ├── preprocess.py          # Module 1 : extraction frames, COCO→YOLO, augmentation
│   ├── dataset.py             # Module 2 : structure YOLO, data.yaml, intégrité
│   ├── train.py               # Module 3 : fine-tuning YOLOv8, callbacks
│   ├── evaluate.py            # Module 4 : évaluation Test (UNE SEULE FOIS)
│   ├── tracker.py             # Module 5 : ByteTrack, IDs persistants, trajectoires
│   ├── counter.py             # Module 6 : lignes virtuelles, comptage directionnel
│   ├── timer.py               # Module 7 : chronomètre par personne, alertes seuils
│   ├── pipeline.py            # Module 8 : Pipeline complet (track + count + timer + face)
│   ├── face_recognition.py    # Module 9 : InsightFace Buffalo, embeddings, identification
│   ├── person_manager.py      # Module 10 : Gestion universelle personnes, profils, rapports
│   ├── student.py             # Wrapper legacy → redirige vers person_manager.py
│   └── report.py              # Module 11 : rapports PDF (ReportLab)
├── api/
│   └── main.py                # FastAPI + WebSockets + JWT
├── app/
│   └── dashboard.py           # Streamlit dashboard temps réel
├── database/
│   └── models.py              # SQLAlchemy (events, alerts, daily_stats)
├── data/
│   ├── download_data.py       # Téléchargement + filtrage COCO
│   ├── faces.db               # Base SQLite des visages enregistrés
│   └── splits/                # Dataset YOLO (images/labels × train/val/test)
├── models/
│   └── finetuned/             # Poids entraînés (best.pt, last.pt)
├── notebooks/
│   └── Surveillance_IA_Train_Colab.ipynb  # Notebook Google Colab optimisé
├── outputs/                   # Rapports, vidéos annotées, snapshots
├── register_faces.py          # ⭐ Outil d'enregistrement de visages (CLI)
├── launch.bat                 # Lancement rapide Windows
├── Dockerfile                 # Multi-stage (API / Dashboard / GPU)
├── docker-compose.yml         # API + Dashboard + PostgreSQL
├── requirements.txt           # Dépendances
└── README.md
```

---

## 🚀 Installation

### Prérequis

- Python 3.10+
- GPU NVIDIA (recommandé) + CUDA 12.x
- PostgreSQL 15+ (ou via Docker)

### Installation locale

```bash
# Cloner le projet
git clone https://github.com/theobawana/surveillance.git
cd surveillance

# Environnement virtuel
python -m venv myenv
source myenv/bin/activate        # Linux/Mac
# myenv\Scripts\Activate.ps1     # Windows PowerShell

# Dépendances
pip install -r requirements.txt
```

### Docker (recommandé)

```bash
# Démarrer (API + Dashboard + PostgreSQL)
docker compose up -d

# Avec GPU
docker compose --profile gpu up -d
```

---

## 📖 Utilisation

### Étape 1 — Enregistrer des visages

Avant de lancer la surveillance, enregistrer les personnes à reconnaître :

```bash
# Menu interactif (recommandé)
python register_faces.py

# Depuis une photo (employé entreprise)
python register_faces.py --photo photo.jpg --nom DUPONT --prenom Jean \
    --groupe "Marketing" --role employe --organisation "SAHELYS"

# Depuis la webcam — VIP pour un événement (5 captures)
python register_faces.py --webcam --nom BAWANA --prenom Theodore \
    --role vip --organisation "Conf Tech 2026" --captures 5

# En lot — employés d'un département (dossier NOM_Prenom_ID/)
python register_faces.py --dossier photos/ \
    --groupe "R&D" --role employe --organisation "SAHELYS"

# En lot — élèves d'une classe (contexte scolaire)
python register_faces.py --dossier photos_classe/ \
    --groupe "6ème A" --role eleve --organisation "Lycée Victor Hugo"

# Lister les personnes enregistrées
python register_faces.py --lister

# Tester la reconnaissance sur une image
python register_faces.py --tester photo_test.jpg

# Tester la reconnaissance en temps réel (webcam)
python register_faces.py --tester-webcam
```

**Structure du dossier pour l'enregistrement en lot :**

```
photos/
├── DUPONT_Jean_001/
│   ├── face1.jpg
│   ├── face2.jpg
│   └── face3.jpg
├── MARTIN_Sophie_002/
│   └── photo.jpg
└── BAWANA_Theodore_003/
    ├── front.jpg
    └── side.jpg
```

### Étape 2 — Lancer la surveillance avec reconnaissance

```bash
# Entreprise — pointage employés (horaires 9h-18h)
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source 0 --show --face \
    --profil entreprise \
    --organisation "SAHELYS"

# Événement — accréditation participants
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source 0 --show --face \
    --profil evenement \
    --organisation "Conf Tech 2026"

# Bâtiment — contrôle d'accès résidents
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source rtsp://cam.local/stream \
    --face --profil batiment \
    --organisation "Résidence Les Pins"

# École — présence élèves (horaires 8h-17h, retards)
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source 0 --show --face \
    --profil ecole \
    --organisation "Lycée Victor Hugo"

# Fichier vidéo + reconnaissance + export
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source video.mp4 \
    --output outputs/result.mp4 \
    --face --profil libre

# Sans reconnaissance (tracking + comptage seuls)
python -m src.pipeline \
    --model models/finetuned/best.pt \
    --source 0 --show

# Lancement rapide Windows
launch.bat
```

**Profils disponibles :**

| Profil | Groupes | Rôles | Horaires |
|--------|---------|-------|----------|
| `ecole` | Classes (6A, 3B...) | eleve, professeur, personnel, directeur | L-V 8h-17h |
| `entreprise` | Départements | employe, manager, directeur, visiteur, stagiaire | L-V 9h-18h |
| `evenement` | Catégories | participant, staff, vip, presse, organisateur | — |
| `batiment` | Étages / Zones | resident, visiteur, livreur, personnel, gardien | — |
| `libre` | Libre | personne | — |

### Étape 3 — Contrôles pendant la surveillance

| Touche | Action |
|--------|--------|
| `Q` | Quitter |
| `R` | Réinitialiser les compteurs |
| `S` | Sauvegarder un snapshot |

### Ce qui s'affiche en temps réel :

- **Barre de stats** (haut) : personnes détectées, IN, OUT, occupation, IDs uniques, FPS, durée
- **Panel IDENTITÉS** (gauche) : liste des personnes reconnues avec % de similarité
- **Panel PRÉSENCE** (droite) : chronomètre de chaque personne active
- **Sur chaque personne** : nom + groupe + % affiché au-dessus de la bbox
- **Lignes virtuelles** : comptage directionnel visible

---

## 🔄 Tracking & Pointage — Comment ça marche

### 1. Après l'enregistrement

Quand vous enregistrez une personne (`register_faces.py`), le système :
- Détecte le visage dans la photo/webcam
- Extrait un **embedding 512D** (vecteur numérique unique du visage)
- Stocke l'embedding + nom + infos dans `data/faces.db` (SQLite)
- Peut stocker **plusieurs embeddings par personne** (de face, de profil, etc.) pour améliorer la précision

### 2. Pendant la surveillance

Pour chaque frame vidéo :

```
Frame → YOLO détecte les personnes
      → ByteTrack attribue un ID de tracking persistant
      → Pour chaque personne détectée :
           → Crop du visage
           → InsightFace extrait l'embedding
           → Comparaison cosinus avec tous les visages enregistrés
           → Si similarité ≥ 45% → IDENTIFIÉ (nom affiché)
           → Sinon → "Inconnu"
```

### 3. Entrées et sorties

```
Personne traverse une ligne virtuelle →
    Direction détectée (IN ou OUT) →
        Si la personne est identifiée →
            ✅ Pointage automatique enregistré :
               - person_id
               - nom, prénom
               - direction (entry/exit)
               - horodatage exact
               - score de similarité
               - caméra
               - retard éventuel (si horaires définis)
```

### 4. Temps de présence

Le `PresenceTimer` calcule automatiquement :
- **Heure d'arrivée** : première détection de la personne
- **Heure de départ** : dernière détection + timeout (10s par défaut)
- **Durée de présence** : départ - arrivée
- **Alertes** : si la personne reste > 1min, 5min, 10min (configurable)

### 5. Rapports générés

À la fin d'une session, le pipeline génère automatiquement :

| Fichier | Contenu |
|---------|---------|
| `rapport_YYYYMMDD_HHMMSS.json` | Rapport complet (comptages, présences, alertes, événements) |
| `passages_YYYYMMDD_HHMMSS.csv` | Historique des passages (ID, direction, heure, ligne, identité) |
| `presence_YYYYMMDD_HHMMSS.csv` | Sessions de présence (entrée, sortie, durée) |

---

## 👤 Gestion des personnes — Multi-secteurs (person_manager.py)

```python
from src.face_recognition import FaceDatabase
from src.person_manager import PersonManager

db = FaceDatabase("data/faces.db")

# ── Exemple 1 : Entreprise ──────────────────────────────────
manager = PersonManager(db, profil="entreprise", organisation="SAHELYS")

manager.inscrire(
    person_id="dupont_jean", nom="DUPONT", prenom="Jean",
    groupe="Marketing", role="employe",
    heure_arrivee="09:00", heure_depart="18:00",
)

# Rapport RH
rapport = manager.rapport_journalier()
print(f"Présents : {rapport['total_presents']}/{rapport['total_inscrits']}")
print(f"Retards  : {rapport['total_retards']}")
manager.export_csv(rapport, "outputs/rapport_rh.csv")

# ── Exemple 2 : Bâtiment / Résidence ────────────────────────
manager_bat = PersonManager(db, profil="batiment", organisation="Résidence Les Pins")

manager_bat.inscrire(
    person_id="martin_s", nom="MARTIN", prenom="Sophie",
    groupe="Bâtiment A - Étage 3", role="resident",
)

# ── Exemple 3 : Événement ────────────────────────────────────
manager_evt = PersonManager(db, profil="evenement", organisation="Conf Tech 2026")

manager_evt.inscrire(
    person_id="speaker_01", nom="BAWANA", prenom="Théodore",
    groupe="Speakers", role="vip",
)

# ── Exemple 4 : École (backward compat) ──────────────────────
from src.person_manager import StudentManager

manager_ecole = StudentManager(db, organisation="Lycée Victor Hugo")
manager_ecole.inscrire_eleve(
    person_id="eleve_001", nom="PETIT", prenom="Lucas",
    classe="6ème A",
)
rapport_classe = manager_ecole.rapport_classe("6ème A")
```

---

## 🔌 Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/auth/token` | Obtenir un token JWT |
| `POST` | `/stream/start` | Démarrer un flux vidéo |
| `POST` | `/stream/stop` | Arrêter un flux vidéo |
| `GET` | `/stream/status` | Statut du flux actif |
| `GET` | `/stream/frame` | Dernière frame annotée (JPEG) |
| `GET` | `/stats` | Statistiques temps réel |
| `GET` | `/alerts` | Alertes actives |
| `GET` | `/events` | Historique des passages |
| `GET` | `/report/{date}` | Rapport quotidien (PDF) |
| `GET` | `/health` | Vérification de santé |
| `WS` | `/ws` | WebSocket temps réel |

### Authentification

```bash
# Obtenir un token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# Utiliser le token
curl -H "Authorization: Bearer <token>" http://localhost:8000/stats
```

---

## 🗄️ Bases de données

### SQLite — Visages & Pointages (`data/faces.db`)

**persons** — Personnes enregistrées

| Colonne | Type | Description |
|---------|------|-------------|
| person_id | TEXT (PK) | Identifiant unique |
| nom | TEXT | Nom de famille |
| prenom | TEXT | Prénom |
| groupe | TEXT | Classe, département, catégorie... |
| role | TEXT | visiteur, employe, eleve, admin... |
| organisation | TEXT | Entreprise, école, club... |
| heure_arrivee_prevue | TEXT | Heure d'arrivée attendue |
| heure_depart_prevue | TEXT | Heure de départ attendue |
| notes | TEXT | Notes libres |
| tags | TEXT | Tags séparés par virgule |
| actif | INT | 1 = actif, 0 = supprimé |

**embeddings** — Vecteurs faciaux

| Colonne | Type | Description |
|---------|------|-------------|
| person_id | TEXT (FK) | Lien vers persons |
| embedding | BLOB | Vecteur 512D (ArcFace) |
| source | TEXT | enrollment, webcam, realtime |

**attendance** — Historique des pointages

| Colonne | Type | Description |
|---------|------|-------------|
| person_id | TEXT (FK) | Personne pointée |
| nom | TEXT | Nom |
| prenom | TEXT | Prénom |
| direction | TEXT | `entry` ou `exit` |
| timestamp | REAL | Timestamp Unix |
| datetime_str | TEXT | Date/heure lisible |
| similarity | REAL | Score de similarité (0-1) |
| camera_id | TEXT | Identifiant caméra |
| is_late | INT | 1 = en retard |
| retard_minutes | REAL | Minutes de retard |

### PostgreSQL — Événements & Stats (API)

**events** — Événements de passage

| Colonne | Type | Description |
|---------|------|-------------|
| person_id | INT | ID tracking |
| direction | VARCHAR | `entry` ou `exit` |
| line_name | VARCHAR | Nom de la ligne virtuelle |
| event_datetime | DATETIME | Horodatage |
| confidence | FLOAT | Score de confiance |

**daily_stats** — Statistiques quotidiennes

| Colonne | Type | Description |
|---------|------|-------------|
| stats_date | DATE | Date |
| total_entries | INT | Total entrées |
| total_exits | INT | Total sorties |
| peak_occupancy | INT | Occupation max |
| avg_presence_time | FLOAT | Temps moyen (s) |

---

## 📋 Datasets supportés

| Dataset | Description | Images |
|---------|-------------|--------|
| **COCO train2017** | Sous-ensemble personnes (~64k images) | Principal |
| **COCO val2017** | Validation + Test (split 50/50) | Val/Test |
| **MOT17** | Multiple Object Tracking Benchmark | Alternatif |
| **VIRAT** | Vidéos de surveillance extérieure | Alternatif |

---

## 🐳 Docker

```bash
# CPU : API (8000) + Dashboard (8501) + PostgreSQL (5432)
docker compose up -d

# GPU : variante CUDA pour l'inférence
docker compose --profile gpu up -d

# Build individuel
docker build --target surv-api -t surveillance-api .
docker build --target surv-dashboard -t surveillance-dashboard .
```

---

## 🔧 Stack technique

| Composant | Technologie |
|-----------|-------------|
| Détection | YOLO v8 Large (Ultralytics) |
| Tracking | ByteTrack (intégré YOLO v8) |
| Reconnaissance faciale | InsightFace Buffalo_l (ArcFace R100, 512D) |
| Deep Learning | PyTorch 2.0+ |
| Vision | OpenCV 4.8+ |
| API | FastAPI + Uvicorn + WebSockets |
| Auth | JWT (python-jose) |
| Dashboard | Streamlit |
| BDD visages | SQLite (faces.db) |
| BDD événements | PostgreSQL 15 + SQLAlchemy 2.0 |
| Rapports | ReportLab + matplotlib |
| Containerisation | Docker multi-stage |
| Entraînement | Google Colab (GPU T4/A100) |

---

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 👤 Auteur

**BAWANA Théodore**

- Portfolio : [theo.portefolio.io](https://theo.portefolio.io)
- GitHub : [github.com/theobawana](https://github.com/theobawana)
- Email : theodore8bawana@gmail.com

*Projet réalisé dans le cadre d'apprentissage de la vision par ordinateur*

---

<div align="center">

**Surveillance-IA** — Intelligence Artificielle au service de la sécurité

*Détection · Tracking · Reconnaissance faciale · Comptage · Pointage · Présence*

</div>
