"""
═══════════════════════════════════════════════════════════════
OUTIL D'ENREGISTREMENT DE VISAGES — Surveillance-IA
═══════════════════════════════════════════════════════════════
Interface CLI interactive pour :
  1. Enregistrer une personne depuis une photo
  2. Enregistrer depuis la webcam (capture en direct)
  3. Enregistrer en lot depuis un dossier
  4. Lister les personnes enregistrées
  5. Supprimer / modifier une personne
  6. Tester la reconnaissance sur une image ou la webcam

Usage :
  python register_faces.py                  → menu interactif
  python register_faces.py --photo face.jpg --nom DUPONT --prenom Jean
  python register_faces.py --webcam --nom DUPONT --prenom Jean
  python register_faces.py --dossier photos/ --groupe "Marketing"
  python register_faces.py --lister
  python register_faces.py --tester photo.jpg
  python register_faces.py --tester-webcam
═══════════════════════════════════════════════════════════════
"""

import os
import sys
import argparse
import time
import logging
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.face_recognition import FaceDatabase, FaceRecognizer, IdentifiedPerson

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# COULEURS TERMINAL
# ═══════════════════════════════════════════════════════════════

class C:
    """Couleurs ANSI pour le terminal."""
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAGENTA = "\033[95m"
    DIM    = "\033[2m"


def banner():
    print(f"""
{C.CYAN}{'═'*65}
  ╔═══════════════════════════════════════════════════════════╗
  ║     SURVEILLANCE-IA — Enregistrement de Visages          ║
  ║     InsightFace Buffalo · Reconnaissance Faciale         ║
  ╚═══════════════════════════════════════════════════════════╝
{'═'*65}{C.RESET}
""")


# ═══════════════════════════════════════════════════════════════
# FONCTIONS D'ENREGISTREMENT
# ═══════════════════════════════════════════════════════════════

def register_from_photo(
    recognizer: FaceRecognizer,
    photo_path: str,
    person_id: str,
    nom: str,
    prenom: str,
    groupe: str = "",
    role: str = "visiteur",
    organisation: str = "",
    **kwargs,
) -> bool:
    """Enregistre une personne depuis un fichier photo."""
    print(f"\n{C.CYAN}📸 Enregistrement depuis photo : {photo_path}{C.RESET}")

    if not os.path.exists(photo_path):
        print(f"{C.RED}  ❌ Fichier non trouvé : {photo_path}{C.RESET}")
        return False

    success = recognizer.enroll_from_image(
        image_path=photo_path,
        person_id=person_id,
        nom=nom,
        prenom=prenom,
        groupe=groupe,
        role=role,
        organisation=organisation,
        **kwargs,
    )

    if success:
        print(f"{C.GREEN}  ✅ {prenom} {nom} enregistré avec succès !{C.RESET}")
        if groupe:
            print(f"     Groupe       : {groupe}")
        if organisation:
            print(f"     Organisation : {organisation}")
        print(f"     Rôle         : {role}")
        print(f"     ID           : {person_id}")
    else:
        print(f"{C.RED}  ❌ Échec de l'enregistrement{C.RESET}")

    return success


def register_from_webcam(
    recognizer: FaceRecognizer,
    person_id: str,
    nom: str,
    prenom: str,
    groupe: str = "",
    role: str = "visiteur",
    organisation: str = "",
    num_captures: int = 5,
    camera_id: int = 0,
    **kwargs,
) -> bool:
    """
    Enregistre une personne via la webcam.

    Capture plusieurs images pour améliorer la robustesse.
    Appuyez sur [ESPACE] pour capturer, [Q] pour quitter.
    """
    print(f"\n{C.CYAN}📹 Enregistrement webcam pour : {prenom} {nom}{C.RESET}")
    print(f"   Appuyez sur {C.BOLD}[ESPACE]{C.RESET} pour capturer ({num_captures} captures demandées)")
    print(f"   Appuyez sur {C.BOLD}[Q]{C.RESET} pour terminer\n")

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"{C.RED}  ❌ Impossible d'ouvrir la webcam (ID: {camera_id}){C.RESET}")
        return False

    # Ajouter la personne en premier
    recognizer.face_db.add_person(
        person_id=person_id,
        nom=nom,
        prenom=prenom,
        groupe=groupe,
        role=role,
        organisation=organisation,
        **kwargs,
    )

    captures = 0
    total_embeddings = 0

    while captures < num_captures:
        ret, frame = cap.read()
        if not ret:
            break

        # Détecter les visages pour le preview
        display = frame.copy()
        faces = recognizer.detect_faces(frame)

        for face in faces:
            x1, y1, x2, y2 = face.bbox
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"Conf: {face.confidence:.2f}"
            if face.age:
                label += f" | Age: {face.age}"
            cv2.putText(
                display, label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 255, 0), 1,
            )

        # Info overlay
        cv2.rectangle(display, (0, 0), (display.shape[1], 50), (50, 50, 50), -1)
        info = (
            f"Enregistrement: {prenom} {nom} | "
            f"Captures: {captures}/{num_captures} | "
            f"[ESPACE] Capturer | [Q] Quitter"
        )
        cv2.putText(
            display, info,
            (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (0, 255, 255), 1,
        )

        cv2.imshow("Enregistrement de Visage", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(" "):
            # Capturer
            if faces:
                face = max(
                    faces,
                    key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]),
                )
                success = recognizer.face_db.add_embedding(
                    person_id=person_id,
                    embedding=face.embedding,
                    source=f"webcam_capture_{captures+1}",
                )
                if success:
                    captures += 1
                    total_embeddings += 1
                    print(f"  📸 Capture {captures}/{num_captures} — OK (conf: {face.confidence:.3f})")

                    # Flash vert
                    flash = display.copy()
                    cv2.rectangle(flash, (0, 0), (flash.shape[1], flash.shape[0]), (0, 255, 0), 10)
                    cv2.imshow("Enregistrement de Visage", flash)
                    cv2.waitKey(200)
            else:
                print(f"  {C.YELLOW}⚠️ Aucun visage détecté, réessayez{C.RESET}")

        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    if total_embeddings > 0:
        recognizer._build_embedding_index()
        print(f"\n{C.GREEN}  ✅ {prenom} {nom} enregistré ! ({total_embeddings} captures){C.RESET}")
        return True
    else:
        print(f"\n{C.RED}  ❌ Aucune capture effectuée{C.RESET}")
        return False


def register_from_directory(
    recognizer: FaceRecognizer,
    directory: str,
    groupe: str = "",
    role: str = "visiteur",
    organisation: str = "",
) -> int:
    """
    Enregistrement en lot depuis un dossier.

    Structure attendue :
        dossier/
        ├── NOM_Prenom_ID/
        │   ├── photo1.jpg
        │   └── photo2.jpg
        ├── BAWANA_Theodore_001/
        │   └── face.jpg
        └── ...
    """
    print(f"\n{C.CYAN}📁 Enregistrement en lot depuis : {directory}{C.RESET}")

    count = recognizer.enroll_from_directory(
        directory=directory,
        groupe=groupe,
        role=role,
        organisation=organisation,
    )

    if count > 0:
        print(f"\n{C.GREEN}  ✅ {count} personne(s) enregistrée(s){C.RESET}")
    else:
        print(f"\n{C.RED}  ❌ Aucune personne enregistrée{C.RESET}")

    return count


def list_persons(face_db: FaceDatabase):
    """Affiche la liste des personnes enregistrées."""
    persons = face_db.get_all_persons()
    embeddings = face_db.get_all_embeddings()

    if not persons:
        print(f"\n{C.YELLOW}  ⚠️ Aucune personne enregistrée{C.RESET}\n")
        return

    print(f"\n{C.CYAN}{'═'*75}")
    print(f"  PERSONNES ENREGISTRÉES ({len(persons)})")
    print(f"{'═'*75}{C.RESET}")
    print(
        f"  {'ID':<20} {'Nom':<15} {'Prénom':<12} "
        f"{'Groupe':<12} {'Rôle':<12} {'Photos':<6}"
    )
    print(f"  {'─'*20} {'─'*15} {'─'*12} {'─'*12} {'─'*12} {'─'*6}")

    for p in sorted(persons, key=lambda x: (x.get("groupe", ""), x.get("nom", ""))):
        pid = p["person_id"]
        n_emb = len(embeddings.get(pid, []))
        print(
            f"  {pid:<20} {p.get('nom',''):<15} {p.get('prenom',''):<12} "
            f"{p.get('groupe','—'):<12} {p.get('role','—'):<12} {n_emb:<6}"
        )

    print(f"  {'─'*75}")
    total_emb = sum(len(v) for v in embeddings.values())
    print(f"  Total: {len(persons)} personnes, {total_emb} embeddings\n")


def delete_person(face_db: FaceDatabase, person_id: str):
    """Supprime une personne."""
    person = face_db.get_person(person_id)
    if not person:
        print(f"{C.RED}  ❌ Personne non trouvée : {person_id}{C.RESET}")
        return

    nom = person.get("prenom", "") + " " + person.get("nom", "")
    confirm = input(f"  Supprimer {nom} ({person_id}) ? [o/N] : ").strip().lower()
    if confirm == "o":
        face_db.delete_person(person_id)
        print(f"{C.GREEN}  ✅ {nom} supprimé{C.RESET}")
    else:
        print("  Annulé.")


def test_recognition_image(recognizer: FaceRecognizer, image_path: str):
    """Teste la reconnaissance sur une image."""
    print(f"\n{C.CYAN}🔍 Test de reconnaissance : {image_path}{C.RESET}\n")

    img = cv2.imread(image_path)
    if img is None:
        print(f"{C.RED}  ❌ Image non trouvée : {image_path}{C.RESET}")
        return

    identified, unknown = recognizer.identify_all(img)

    if identified:
        print(f"  {C.GREEN}✅ {len(identified)} personne(s) identifiée(s) :{C.RESET}")
        for p in identified:
            label = f"    • {p.full_name}"
            if p.groupe:
                label += f" ({p.groupe})"
            if p.organisation:
                label += f" [{p.organisation}]"
            label += f" — similarité: {p.similarity:.1%}"
            print(label)
    else:
        print(f"  {C.YELLOW}⚠️ Aucune personne reconnue{C.RESET}")

    if unknown:
        print(f"  {C.RED}❓ {len(unknown)} visage(s) inconnu(s){C.RESET}")

    # Afficher l'image annotée
    annotated = recognizer.draw_identifications(img, identified, unknown)
    cv2.imshow("Test Reconnaissance", annotated)
    print(f"\n  Appuyez sur une touche pour fermer...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_recognition_webcam(recognizer: FaceRecognizer, camera_id: int = 0):
    """Teste la reconnaissance en temps réel via webcam."""
    print(f"\n{C.CYAN}🔍 Test reconnaissance temps réel (webcam){C.RESET}")
    print(f"   Appuyez sur {C.BOLD}[Q]{C.RESET} pour quitter\n")

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"{C.RED}  ❌ Impossible d'ouvrir la webcam{C.RESET}")
        return

    fps_counter = 0
    fps_time = time.time()
    fps_display = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Reconnaissance
        identified, unknown = recognizer.identify_all(frame)

        # Dessiner
        display = recognizer.draw_identifications(frame, identified, unknown)

        # FPS
        fps_counter += 1
        if time.time() - fps_time >= 1.0:
            fps_display = fps_counter
            fps_counter = 0
            fps_time = time.time()

        # Overlay
        cv2.rectangle(display, (0, 0), (display.shape[1], 40), (50, 50, 50), -1)
        info = f"Reconnaissance | Identifiés: {len(identified)} | Inconnus: {len(unknown)} | FPS: {fps_display}"
        cv2.putText(
            display, info,
            (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
            (0, 255, 0), 1,
        )

        cv2.imshow("Test Reconnaissance Temps Réel", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


# ═══════════════════════════════════════════════════════════════
# MENU INTERACTIF
# ═══════════════════════════════════════════════════════════════

def interactive_menu(recognizer: FaceRecognizer):
    """Menu interactif pour l'enregistrement."""
    while True:
        print(f"\n{C.CYAN}{'─'*50}")
        print(f"  MENU PRINCIPAL")
        print(f"{'─'*50}{C.RESET}")
        print(f"  {C.GREEN}1{C.RESET}. Enregistrer depuis une photo")
        print(f"  {C.GREEN}2{C.RESET}. Enregistrer depuis la webcam")
        print(f"  {C.GREEN}3{C.RESET}. Enregistrement en lot (dossier)")
        print(f"  {C.GREEN}4{C.RESET}. Lister les personnes enregistrées")
        print(f"  {C.GREEN}5{C.RESET}. Supprimer une personne")
        print(f"  {C.GREEN}6{C.RESET}. Tester la reconnaissance (image)")
        print(f"  {C.GREEN}7{C.RESET}. Tester la reconnaissance (webcam)")
        print(f"  {C.GREEN}8{C.RESET}. Recharger l'index")
        print(f"  {C.RED}0{C.RESET}. Quitter")
        print()

        choix = input(f"  Choix → ").strip()

        if choix == "1":
            # Photo
            photo = input("  Chemin de la photo : ").strip().strip('"')
            nom = input("  Nom : ").strip()
            prenom = input("  Prénom : ").strip()
            pid = input(f"  ID [{nom.lower()}_{prenom.lower()}] : ").strip()
            if not pid:
                pid = f"{nom.lower()}_{prenom.lower()}"
            groupe = input("  Groupe/Classe/Département (optionnel) : ").strip()
            role = input("  Rôle [visiteur] : ").strip() or "visiteur"
            org = input("  Organisation (optionnel) : ").strip()

            register_from_photo(
                recognizer, photo, pid, nom, prenom,
                groupe=groupe, role=role, organisation=org,
            )

        elif choix == "2":
            # Webcam
            nom = input("  Nom : ").strip()
            prenom = input("  Prénom : ").strip()
            pid = input(f"  ID [{nom.lower()}_{prenom.lower()}] : ").strip()
            if not pid:
                pid = f"{nom.lower()}_{prenom.lower()}"
            groupe = input("  Groupe/Classe/Département (optionnel) : ").strip()
            role = input("  Rôle [visiteur] : ").strip() or "visiteur"
            org = input("  Organisation (optionnel) : ").strip()
            n = input("  Nombre de captures [5] : ").strip()
            n = int(n) if n.isdigit() else 5

            register_from_webcam(
                recognizer, pid, nom, prenom,
                groupe=groupe, role=role, organisation=org,
                num_captures=n,
            )

        elif choix == "3":
            # Dossier
            dossier = input("  Chemin du dossier : ").strip().strip('"')
            groupe = input("  Groupe par défaut (optionnel) : ").strip()
            role = input("  Rôle par défaut [visiteur] : ").strip() or "visiteur"
            org = input("  Organisation (optionnel) : ").strip()

            register_from_directory(
                recognizer, dossier,
                groupe=groupe, role=role, organisation=org,
            )

        elif choix == "4":
            list_persons(recognizer.face_db)

        elif choix == "5":
            list_persons(recognizer.face_db)
            pid = input("  ID de la personne à supprimer : ").strip()
            if pid:
                delete_person(recognizer.face_db, pid)

        elif choix == "6":
            photo = input("  Chemin de l'image : ").strip().strip('"')
            if photo:
                test_recognition_image(recognizer, photo)

        elif choix == "7":
            test_recognition_webcam(recognizer)

        elif choix == "8":
            recognizer.refresh_index()
            print(f"  {C.GREEN}✅ Index rechargé{C.RESET}")

        elif choix == "0":
            print(f"\n{C.CYAN}  Au revoir !{C.RESET}\n")
            break

        else:
            print(f"  {C.YELLOW}⚠️ Choix invalide{C.RESET}")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Surveillance-IA — Enregistrement et gestion des visages",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Base de données
    parser.add_argument(
        "--db", default="data/faces.db",
        help="Chemin vers la base SQLite (défaut: data/faces.db)",
    )
    parser.add_argument(
        "--model", default="buffalo_l",
        choices=["buffalo_l", "buffalo_s", "buffalo_sc"],
        help="Modèle InsightFace (défaut: buffalo_l)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.45,
        help="Seuil de similarité (défaut: 0.45)",
    )

    # Modes
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--photo", metavar="IMAGE",
        help="Enregistrer depuis une photo",
    )
    group.add_argument(
        "--webcam", action="store_true",
        help="Enregistrer depuis la webcam",
    )
    group.add_argument(
        "--dossier", metavar="DIR",
        help="Enregistrement en lot depuis un dossier",
    )
    group.add_argument(
        "--lister", action="store_true",
        help="Lister les personnes enregistrées",
    )
    group.add_argument(
        "--supprimer", metavar="ID",
        help="Supprimer une personne par son ID",
    )
    group.add_argument(
        "--tester", metavar="IMAGE",
        help="Tester la reconnaissance sur une image",
    )
    group.add_argument(
        "--tester-webcam", action="store_true",
        help="Tester la reconnaissance en temps réel (webcam)",
    )

    # Infos de la personne
    parser.add_argument("--nom", default="", help="Nom de famille")
    parser.add_argument("--prenom", default="", help="Prénom")
    parser.add_argument("--id", dest="person_id", default="", help="ID unique")
    parser.add_argument("--groupe", default="", help="Groupe / Classe / Département")
    parser.add_argument("--role", default="visiteur", help="Rôle (visiteur, employe, eleve, admin...)")
    parser.add_argument("--organisation", default="", help="Organisation")
    parser.add_argument("--captures", type=int, default=5, help="Nombre de captures webcam (défaut: 5)")
    parser.add_argument("--camera", type=int, default=0, help="ID de la caméra (défaut: 0)")

    args = parser.parse_args()

    banner()

    # Initialiser
    print(f"{C.DIM}  Initialisation de la base de données...{C.RESET}")
    face_db = FaceDatabase(db_path=args.db)

    print(f"{C.DIM}  Chargement du modèle InsightFace ({args.model})...{C.RESET}")
    recognizer = FaceRecognizer(
        face_db=face_db,
        model_name=args.model,
        similarity_threshold=args.threshold,
    )

    # Auto-générer l'ID si non fourni
    if not args.person_id and args.nom and args.prenom:
        args.person_id = f"{args.nom.lower()}_{args.prenom.lower()}"

    # Exécuter l'action
    if args.photo:
        if not args.nom or not args.prenom:
            print(f"{C.RED}  ❌ --nom et --prenom sont requis pour l'enregistrement{C.RESET}")
            sys.exit(1)
        register_from_photo(
            recognizer, args.photo,
            args.person_id, args.nom, args.prenom,
            groupe=args.groupe, role=args.role,
            organisation=args.organisation,
        )

    elif args.webcam:
        if not args.nom or not args.prenom:
            print(f"{C.RED}  ❌ --nom et --prenom sont requis pour l'enregistrement{C.RESET}")
            sys.exit(1)
        register_from_webcam(
            recognizer, args.person_id, args.nom, args.prenom,
            groupe=args.groupe, role=args.role,
            organisation=args.organisation,
            num_captures=args.captures,
            camera_id=args.camera,
        )

    elif args.dossier:
        register_from_directory(
            recognizer, args.dossier,
            groupe=args.groupe, role=args.role,
            organisation=args.organisation,
        )

    elif args.lister:
        list_persons(face_db)

    elif args.supprimer:
        delete_person(face_db, args.supprimer)

    elif args.tester:
        test_recognition_image(recognizer, args.tester)

    elif args.tester_webcam:
        test_recognition_webcam(recognizer, camera_id=args.camera)

    else:
        # Menu interactif
        interactive_menu(recognizer)


if __name__ == "__main__":
    main()
