"""
═══════════════════════════════════════════════════════════════
TÉLÉCHARGEMENT & PRÉPARATION DES DONNÉES — Surveillance-IA
═══════════════════════════════════════════════════════════════
Télécharge COCO 2017 (subset personnes), convertit en YOLO,
sépare Train/Val/Test et lance le pipeline complet.

Usage :
    # Télécharger COCO val2017 (petit, ~1 Go — pour tester)
    python data/download_data.py --subset val

    # Télécharger COCO train2017 + val2017 (complet, ~20 Go)
    python data/download_data.py --subset all

    # Seulement les annotations (si images déjà présentes)
    python data/download_data.py --annotations-only

    # Pipeline complète après téléchargement
    python data/download_data.py --subset val --pipeline
═══════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import shutil
import zipfile
import hashlib
import logging
import argparse
import urllib.request
from pathlib import Path
from typing import Optional, Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── URLs officielles COCO 2017 ─────────────────────────────
COCO_URLS = {
    "train_images": {
        "url": "http://images.cocodataset.org/zips/train2017.zip",
        "size": "~18 Go",
        "md5": None,
    },
    "val_images": {
        "url": "http://images.cocodataset.org/zips/val2017.zip",
        "size": "~1 Go",
        "md5": None,
    },
    "annotations": {
        "url": "http://images.cocodataset.org/annotations/annotations_trainval2017.zip",
        "size": "~252 Mo",
        "md5": None,
    },
}

# ─── Chemins par défaut ──────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
COCO_DIR = RAW_DIR / "coco2017"
SPLITS_DIR = BASE_DIR / "splits"


def download_file(url: str, dest: Path, desc: str = "") -> Path:
    """
    Télécharge un fichier avec barre de progression.
    Reprend le téléchargement si le fichier existe déjà partiellement.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        logger.info(f"✅ Déjà téléchargé : {dest.name}")
        return dest

    logger.info(f"⬇️  Téléchargement de {desc or dest.name}…")
    logger.info(f"   URL : {url}")

    try:
        # Obtenir la taille totale
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            total_mb = total_size / (1024 * 1024)

            logger.info(f"   Taille : {total_mb:.1f} Mo")

            # Télécharger par blocs
            temp_dest = dest.with_suffix(dest.suffix + ".tmp")
            block_size = 1024 * 1024  # 1 Mo
            downloaded = 0

            with open(temp_dest, "wb") as f:
                while True:
                    block = response.read(block_size)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)
                    pct = (downloaded / total_size * 100) if total_size > 0 else 0
                    print(
                        f"\r   Progression : {downloaded / (1024*1024):.1f} Mo "
                        f"/ {total_mb:.1f} Mo ({pct:.1f}%)",
                        end="", flush=True,
                    )

            print()  # Nouvelle ligne après la barre
            temp_dest.rename(dest)
            logger.info(f"✅ Téléchargement terminé : {dest.name}")

    except Exception as e:
        logger.error(f"❌ Erreur de téléchargement : {e}")
        raise

    return dest


def extract_zip(zip_path: Path, extract_to: Path, desc: str = "") -> Path:
    """Extrait un fichier ZIP."""
    logger.info(f"📦 Extraction de {desc or zip_path.name}…")

    if not zip_path.exists():
        raise FileNotFoundError(f"Archive non trouvée : {zip_path}")

    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)

    logger.info(f"✅ Extraction terminée dans {extract_to}")
    return extract_to


def download_coco_annotations() -> Path:
    """Télécharge et extrait les annotations COCO 2017."""
    info = COCO_URLS["annotations"]
    zip_path = RAW_DIR / "annotations_trainval2017.zip"

    download_file(info["url"], zip_path, f"Annotations COCO 2017 ({info['size']})")

    # Extraire
    ann_dir = COCO_DIR / "annotations"
    if not ann_dir.exists():
        extract_zip(zip_path, COCO_DIR, "Annotations COCO 2017")

    return ann_dir


def download_coco_images(subset: str = "val") -> Path:
    """
    Télécharge et extrait les images COCO 2017.

    Args:
        subset: 'val' (~5K images, 1 Go) ou 'train' (~118K images, 18 Go)
    """
    key = f"{subset}_images"
    if key not in COCO_URLS:
        raise ValueError(f"Subset inconnu : {subset}. Valeurs : val, train")

    info = COCO_URLS[key]
    zip_path = RAW_DIR / f"{subset}2017.zip"

    download_file(info["url"], zip_path, f"Images COCO {subset}2017 ({info['size']})")

    # Extraire
    images_dir = COCO_DIR / f"{subset}2017"
    if not images_dir.exists():
        extract_zip(zip_path, COCO_DIR, f"Images COCO {subset}2017")

    return images_dir


def filter_coco_people(
    annotations_dir: Path,
    subset: str = "val",
) -> tuple:
    """
    Filtre les annotations COCO pour ne garder que la catégorie 'person'.

    Returns:
        (filtered_json_path, num_images, num_annotations)
    """
    ann_file = annotations_dir / f"instances_{subset}2017.json"
    if not ann_file.exists():
        raise FileNotFoundError(f"Fichier d'annotations non trouvé : {ann_file}")

    logger.info(f"🔍 Filtrage des personnes dans {ann_file.name}…")

    with open(ann_file, "r", encoding="utf-8") as f:
        coco = json.load(f)

    # Trouver l'ID de la catégorie "person"
    person_cat_ids = [
        c["id"] for c in coco["categories"]
        if c["name"] == "person"
    ]

    if not person_cat_ids:
        raise ValueError("Catégorie 'person' non trouvée dans les annotations COCO")

    # Filtrer annotations
    person_anns = [
        ann for ann in coco["annotations"]
        if ann["category_id"] in person_cat_ids
        and ann.get("iscrowd", 0) == 0  # Ignorer les annotations crowd
        and ann["area"] > 1024  # Ignorer les très petites annotations (< 32×32)
    ]

    # Images correspondantes
    person_img_ids = {ann["image_id"] for ann in person_anns}
    person_images = [
        img for img in coco["images"]
        if img["id"] in person_img_ids
    ]

    # Sauvegarder le JSON filtré
    filtered = {
        "images": person_images,
        "annotations": person_anns,
        "categories": [
            c for c in coco["categories"]
            if c["id"] in person_cat_ids
        ],
    }

    output_path = annotations_dir / f"instances_{subset}2017_people.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f)

    logger.info(
        f"✅ Filtrage terminé :\n"
        f"   Images avec personnes : {len(person_images)}\n"
        f"   Annotations personnes : {len(person_anns)}\n"
        f"   Sauvegardé : {output_path}"
    )

    return output_path, len(person_images), len(person_anns)


def run_pipeline(
    coco_json: Path,
    images_dir: Path,
    output_dir: Path = SPLITS_DIR,
    no_augment: bool = False,
) -> Dict:
    """
    Lance la pipeline complète : COCO → YOLO → Split → Augment → data.yaml.
    """
    # Ajouter le dossier parent au path pour les imports
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    from src.dataset import DatasetPipeline

    logger.info("\n" + "=" * 60)
    logger.info("  🚀 LANCEMENT PIPELINE COMPLÈTE")
    logger.info("=" * 60)

    pipeline = DatasetPipeline(str(output_dir))
    result = pipeline.prepare_from_coco(
        str(coco_json),
        str(images_dir),
        augment_train=not no_augment,
    )

    logger.info("\n" + "=" * 60)
    logger.info("  ✅ PIPELINE TERMINÉE")
    logger.info(f"  Dataset prêt dans : {output_dir}")
    logger.info(f"  Fichier config    : {output_dir / 'data.yaml'}")
    logger.info("=" * 60)

    return result


def print_summary():
    """Affiche un résumé du dataset disponible."""
    print("\n" + "=" * 60)
    print("  RÉSUMÉ DES DONNÉES — Surveillance-IA")
    print("=" * 60)

    # Vérifier COCO
    for subset in ["val", "train"]:
        img_dir = COCO_DIR / f"{subset}2017"
        if img_dir.exists():
            n_images = len(list(img_dir.glob("*.jpg")))
            print(f"\n  📁 COCO {subset}2017 : {n_images} images")
        else:
            print(f"\n  ❌ COCO {subset}2017 : non téléchargé")

    # Vérifier annotations
    ann_dir = COCO_DIR / "annotations"
    if ann_dir.exists():
        for f in sorted(ann_dir.glob("*.json")):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  📄 {f.name} ({size_mb:.1f} Mo)")
    else:
        print("  ❌ Annotations : non téléchargées")

    # Vérifier splits
    if SPLITS_DIR.exists():
        for split in ["train", "val", "test"]:
            img_split = SPLITS_DIR / "images" / split
            lbl_split = SPLITS_DIR / "labels" / split
            if img_split.exists():
                n_img = len(list(img_split.iterdir()))
                n_lbl = len(list(lbl_split.iterdir())) if lbl_split.exists() else 0
                print(f"\n  📂 {split:5s} : {n_img} images, {n_lbl} labels")

        yaml_path = SPLITS_DIR / "data.yaml"
        if yaml_path.exists():
            print(f"\n  ✅ data.yaml : prêt")
        else:
            print(f"\n  ❌ data.yaml : non généré")
    else:
        print("\n  ❌ Dataset YOLO : non préparé (lancer --pipeline)")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Téléchargement et préparation des données — Surveillance-IA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Tester avec COCO val2017 (~1 Go, ~2.7K images de personnes)
  python data/download_data.py --subset val --pipeline

  # Dataset complet COCO train+val (~20 Go, ~64K images de personnes)
  python data/download_data.py --subset all --pipeline

  # Voir l'état actuel des données
  python data/download_data.py --status

  # Télécharger sans lancer la pipeline
  python data/download_data.py --subset val
        """,
    )

    parser.add_argument(
        "--subset",
        choices=["val", "train", "all"],
        default="val",
        help="Subset COCO à télécharger : val (~1 Go), train (~18 Go), all (les deux)",
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Lancer la pipeline complète après téléchargement (convert → split → augment → yaml)",
    )
    parser.add_argument(
        "--no-augment",
        action="store_true",
        help="Désactiver l'augmentation de données (plus rapide)",
    )
    parser.add_argument(
        "--annotations-only",
        action="store_true",
        help="Télécharger uniquement les annotations (si images déjà présentes)",
    )
    parser.add_argument(
        "--output",
        default=str(SPLITS_DIR),
        help=f"Dossier de sortie pour le dataset YOLO (défaut : {SPLITS_DIR})",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Afficher l'état actuel des données et quitter",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Supprimer les fichiers ZIP après extraction",
    )

    args = parser.parse_args()

    # ── Status ──
    if args.status:
        print_summary()
        return

    print("\n" + "=" * 60)
    print("  📥 TÉLÉCHARGEMENT DONNÉES — Surveillance-IA")
    print("=" * 60)

    # ── Téléchargement annotations ──
    ann_dir = download_coco_annotations()

    # ── Téléchargement images ──
    if not args.annotations_only:
        if args.subset in ("val", "all"):
            val_dir = download_coco_images("val")

        if args.subset in ("train", "all"):
            train_dir = download_coco_images("train")

    # ── Filtrage personnes ──
    subsets_to_filter = []
    if args.subset in ("val", "all"):
        subsets_to_filter.append("val")
    if args.subset in ("train", "all"):
        subsets_to_filter.append("train")

    filtered_jsons = {}
    for subset in subsets_to_filter:
        filt_path, n_img, n_ann = filter_coco_people(ann_dir, subset)
        filtered_jsons[subset] = filt_path
        logger.info(f"   {subset}: {n_img} images, {n_ann} annotations")

    # ── Nettoyage ZIP ──
    if args.clean:
        logger.info("🧹 Nettoyage des fichiers ZIP…")
        for zip_file in RAW_DIR.glob("*.zip"):
            zip_file.unlink()
            logger.info(f"   Supprimé : {zip_file.name}")

    # ── Pipeline ──
    if args.pipeline:
        # Utiliser val par défaut, ou train si subset=train
        if "val" in filtered_jsons:
            primary_subset = "val"
        else:
            primary_subset = "train"

        coco_json = filtered_jsons[primary_subset]
        images_dir = COCO_DIR / f"{primary_subset}2017"
        output_dir = Path(args.output)

        run_pipeline(
            coco_json,
            images_dir,
            output_dir,
            no_augment=args.no_augment,
        )

    # ── Résumé final ──
    print_summary()

    if not args.pipeline:
        print("\n💡 Pour lancer la pipeline complète :")
        print(f"   python data/download_data.py --subset {args.subset} --pipeline\n")


if __name__ == "__main__":
    main()
