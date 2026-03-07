"""
═══════════════════════════════════════════════════════════════
MODULE 2 — Gestion du Dataset YOLO v8
═══════════════════════════════════════════════════════════════
- Structure de dossiers YOLO v8 (images/{train,val,test}, labels/…)
- Génération automatique de data.yaml
- Vérification d'intégrité du dataset
- Support datasets : MOT17, COCO People, VIRAT, Oxford Town Centre
═══════════════════════════════════════════════════════════════
"""

import os
import yaml
import json
import shutil
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────
CLASS_NAMES = ["person"]
NUM_CLASSES = len(CLASS_NAMES)


# ═══════════════════════════════════════════════════════════════
# 1. GESTIONNAIRE DE STRUCTURE YOLO
# ═══════════════════════════════════════════════════════════════

class YOLODatasetBuilder:
    """
    Crée et gère la structure de dossiers requise par YOLO v8 :

        dataset_root/
        ├── data.yaml
        ├── images/
        │   ├── train/
        │   ├── val/
        │   └── test/
        └── labels/
            ├── train/
            ├── val/
            └── test/
    """

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def create_structure(self) -> None:
        """Crée l'arborescence de dossiers YOLO."""
        for split in ["train", "val", "test"]:
            (self.root_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.root_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        logger.info(f"✅ Structure YOLO créée dans {self.root_dir}")

    def generate_data_yaml(
        self,
        yaml_path: Optional[str] = None,
    ) -> str:
        """
        Génère le fichier data.yaml nécessaire à l'entraînement YOLO v8.

        Returns:
            Chemin du fichier yaml généré.
        """
        if yaml_path is None:
            yaml_path = str(self.root_dir / "data.yaml")

        # Chemins absolus pour compatibilité cross-plateforme
        data_config = {
            "path": str(self.root_dir.resolve()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": NUM_CLASSES,
            "names": CLASS_NAMES,
        }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data_config, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"✅ data.yaml généré : {yaml_path}")
        return yaml_path

    def get_split_stats(self) -> Dict[str, Dict]:
        """
        Calcule les statistiques par split.

        Returns:
            {split: {images: int, labels: int, total_bboxes: int, ...}}
        """
        stats = {}
        for split in ["train", "val", "test"]:
            img_dir = self.root_dir / "images" / split
            lbl_dir = self.root_dir / "labels" / split

            n_images = len(list(img_dir.glob("*.*"))) if img_dir.exists() else 0
            n_labels = len(list(lbl_dir.glob("*.txt"))) if lbl_dir.exists() else 0

            total_bboxes = 0
            class_counts = Counter()

            if lbl_dir.exists():
                for label_file in lbl_dir.glob("*.txt"):
                    with open(label_file, "r") as f:
                        for line in f:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                total_bboxes += 1
                                cls_id = int(parts[0])
                                class_counts[cls_id] += 1

            stats[split] = {
                "images": n_images,
                "labels": n_labels,
                "total_bboxes": total_bboxes,
                "class_distribution": dict(class_counts),
                "avg_bboxes_per_image": (
                    round(total_bboxes / max(n_labels, 1), 2)
                ),
            }

        return stats

    def print_stats(self) -> None:
        """Affiche les statistiques du dataset."""
        stats = self.get_split_stats()
        print("\n" + "=" * 60)
        print("  STATISTIQUES DATASET YOLO v8 — Surveillance-IA")
        print("=" * 60)

        for split, s in stats.items():
            print(f"\n  [{split.upper()}]")
            print(f"    Images      : {s['images']}")
            print(f"    Labels      : {s['labels']}")
            print(f"    Total BBoxes: {s['total_bboxes']}")
            print(f"    Avg BBox/img: {s['avg_bboxes_per_image']}")
            if s["class_distribution"]:
                for cls_id, count in s["class_distribution"].items():
                    cls_name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
                    print(f"    - {cls_name}: {count}")

        total_imgs = sum(s["images"] for s in stats.values())
        if total_imgs > 0:
            print(f"\n  [RATIOS]")
            for split, s in stats.items():
                ratio = s["images"] / total_imgs * 100
                print(f"    {split}: {ratio:.1f}%")

        print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════
# 2. VÉRIFICATION D'INTÉGRITÉ
# ═══════════════════════════════════════════════════════════════

class DatasetIntegrityChecker:
    """
    Vérifie l'intégrité complète du dataset :
    - Correspondance images ↔ labels
    - Format des annotations
    - Absence de fuites entre splits
    """

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def check_all(self) -> Dict[str, any]:
        """Exécute toutes les vérifications d'intégrité."""
        report = {
            "data_yaml_exists": False,
            "splits": {},
            "data_leakage": False,
            "overall_ok": True,
            "issues": [],
        }

        # Vérifier data.yaml
        yaml_path = self.root_dir / "data.yaml"
        report["data_yaml_exists"] = yaml_path.exists()
        if not yaml_path.exists():
            report["issues"].append("data.yaml manquant")
            report["overall_ok"] = False

        # Vérifier chaque split
        all_image_hashes = {}
        for split in ["train", "val", "test"]:
            split_report = self._check_split(split)
            report["splits"][split] = split_report
            if not split_report["ok"]:
                report["overall_ok"] = False

            # Collecter noms de fichiers pour détecter les fuites
            all_image_hashes[split] = set(split_report.get("image_stems", []))

        # Vérifier les fuites de données entre splits
        for s1 in ["train", "val", "test"]:
            for s2 in ["train", "val", "test"]:
                if s1 >= s2:
                    continue
                overlap = all_image_hashes[s1] & all_image_hashes[s2]
                if overlap:
                    report["data_leakage"] = True
                    report["overall_ok"] = False
                    report["issues"].append(
                        f"⚠️ FUITE de données {s1}↔{s2}: "
                        f"{len(overlap)} images communes"
                    )

        if report["overall_ok"]:
            logger.info("✅ Intégrité du dataset vérifiée : OK")
        else:
            logger.warning(
                f"⚠️ {len(report['issues'])} problèmes détectés"
            )

        return report

    def _check_split(self, split: str) -> Dict:
        """Vérifie un split individuel."""
        img_dir = self.root_dir / "images" / split
        lbl_dir = self.root_dir / "labels" / split

        result = {
            "ok": True,
            "image_stems": [],
            "images_count": 0,
            "labels_count": 0,
            "missing_labels": [],
            "orphan_labels": [],
            "invalid_labels": [],
        }

        if not img_dir.exists():
            result["ok"] = False
            return result

        img_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
        image_stems = {
            f.stem for f in img_dir.iterdir()
            if f.suffix.lower() in img_extensions
        }
        label_stems = set()
        if lbl_dir.exists():
            label_stems = {
                f.stem for f in lbl_dir.iterdir()
                if f.suffix == ".txt"
            }

        result["images_count"] = len(image_stems)
        result["labels_count"] = len(label_stems)
        result["image_stems"] = list(image_stems)
        result["missing_labels"] = list(image_stems - label_stems)
        result["orphan_labels"] = list(label_stems - image_stems)

        # Vérifier le format des labels
        for stem in (image_stems & label_stems):
            label_path = lbl_dir / f"{stem}.txt"
            try:
                with open(label_path, "r") as f:
                    for line_num, line in enumerate(f, 1):
                        parts = line.strip().split()
                        if not parts:
                            continue
                        if len(parts) != 5:
                            result["invalid_labels"].append(
                                f"{stem}.txt L{line_num}"
                            )
                            result["ok"] = False
            except Exception as e:
                result["invalid_labels"].append(f"{stem}.txt: {e}")
                result["ok"] = False

        if result["missing_labels"]:
            result["ok"] = False

        return result


# ═══════════════════════════════════════════════════════════════
# 3. SUPPORT MULTI-DATASETS
# ═══════════════════════════════════════════════════════════════

class DatasetDownloader:
    """
    Gestionnaire de téléchargement et préparation des datasets
    supportés : MOT17, COCO People, VIRAT, Oxford Town Centre.
    """

    DATASETS_INFO = {
        "mot17": {
            "name": "MOT17 — Multiple Object Tracking Benchmark",
            "url": "https://motchallenge.net/data/MOT17/",
            "description": "7 séquences de surveillance, personnes annotées",
            "format": "MOT (CSV)",
        },
        "coco_people": {
            "name": "COCO People Subset",
            "url": "https://cocodataset.org/#download",
            "description": "Images COCO filtrées pour la catégorie « person »",
            "format": "COCO JSON",
        },
        "virat": {
            "name": "VIRAT Video Dataset",
            "url": "https://viratdata.org/",
            "description": "Séquences vidéo de surveillance en extérieur",
            "format": "Annotations propriétaires",
        },
        "oxford_town_centre": {
            "name": "Oxford Town Centre Dataset",
            "url": "https://megapixels.cc/oxford_town_centre/",
            "description": "Vue plongeante de rue piétonne",
            "format": "CSV (head positions)",
        },
    }

    @classmethod
    def list_datasets(cls) -> None:
        """Affiche les datasets disponibles."""
        print("\n" + "=" * 60)
        print("  DATASETS DISPONIBLES — Surveillance-IA")
        print("=" * 60)
        for key, info in cls.DATASETS_INFO.items():
            print(f"\n  [{key}]")
            print(f"    Nom    : {info['name']}")
            print(f"    URL    : {info['url']}")
            print(f"    Desc   : {info['description']}")
            print(f"    Format : {info['format']}")
        print("=" * 60 + "\n")

    @staticmethod
    def convert_mot_to_yolo(
        mot_dir: str,
        output_dir: str,
        img_width: int = 1920,
        img_height: int = 1080,
    ) -> int:
        """
        Convertit les annotations MOT17 (CSV) en format YOLO.

        Format MOT17 : frame, id, bb_left, bb_top, bb_width, bb_height,
                       conf, x, y, z

        Returns:
            Nombre de frames annotées.
        """
        os.makedirs(output_dir, exist_ok=True)

        gt_file = os.path.join(mot_dir, "gt", "gt.txt")
        if not os.path.exists(gt_file):
            logger.error(f"Fichier ground truth non trouvé : {gt_file}")
            return 0

        # Regrouper par frame
        frames = {}
        with open(gt_file, "r") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 7:
                    continue
                frame_id = int(parts[0])
                # Ignorer les annotations avec conf <= 0 (distractors)
                conf = float(parts[6])
                if conf <= 0:
                    continue

                bb_left = float(parts[2])
                bb_top = float(parts[3])
                bb_width = float(parts[4])
                bb_height = float(parts[5])

                if frame_id not in frames:
                    frames[frame_id] = []

                # Convertir en YOLO (normalisé)
                x_center = (bb_left + bb_width / 2) / img_width
                y_center = (bb_top + bb_height / 2) / img_height
                w = bb_width / img_width
                h = bb_height / img_height

                frames[frame_id].append(
                    f"0 {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}"
                )

        # Écrire les fichiers label
        for frame_id, annotations in frames.items():
            label_path = os.path.join(output_dir, f"{frame_id:06d}.txt")
            with open(label_path, "w") as f:
                f.write("\n".join(annotations) + "\n")

        logger.info(f"✅ MOT → YOLO : {len(frames)} frames annotées")
        return len(frames)

    @staticmethod
    def filter_coco_people(
        coco_json_path: str,
        output_json_path: str,
    ) -> int:
        """
        Filtre un fichier COCO JSON pour ne garder que la catégorie person.

        Returns:
            Nombre d'images contenant des personnes.
        """
        with open(coco_json_path, "r", encoding="utf-8") as f:
            coco = json.load(f)

        # Garder la catégorie person
        person_cat_ids = [
            c["id"] for c in coco["categories"]
            if c["name"] == "person"
        ]

        # Filtrer les annotations
        person_annotations = [
            ann for ann in coco["annotations"]
            if ann["category_id"] in person_cat_ids
        ]

        # IDs d'images qui contiennent des personnes
        person_image_ids = {ann["image_id"] for ann in person_annotations}

        # Filtrer les images
        person_images = [
            img for img in coco["images"]
            if img["id"] in person_image_ids
        ]

        # Résultat filtré
        filtered = {
            "images": person_images,
            "annotations": person_annotations,
            "categories": [
                c for c in coco["categories"]
                if c["id"] in person_cat_ids
            ],
        }

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(filtered, f)

        logger.info(
            f"✅ COCO filtré : {len(person_images)} images, "
            f"{len(person_annotations)} annotations de personnes"
        )
        return len(person_images)


# ═══════════════════════════════════════════════════════════════
# 4. PIPELINE COMPLÈTE
# ═══════════════════════════════════════════════════════════════

class DatasetPipeline:
    """
    Pipeline complète : téléchargement → extraction → conversion
    → split → augmentation → data.yaml.
    """

    def __init__(self, output_dir: str = "data/splits"):
        self.output_dir = output_dir
        self.builder = YOLODatasetBuilder(output_dir)
        self.checker = DatasetIntegrityChecker(output_dir)

    def prepare_from_coco(
        self,
        coco_json: str,
        images_dir: str,
        augment_train: bool = True,
        num_augmentations: int = 2,
    ) -> Dict:
        """
        Pipeline complète depuis un dataset COCO.

        Steps:
            1. Filtrer catégorie « person »
            2. Convertir annotations COCO → YOLO
            3. Créer la structure YOLO
            4. Séparer Train/Val/Test (70/15/15)
            5. Augmenter le Train UNIQUEMENT
            6. Générer data.yaml
            7. Vérifier l'intégrité
        """
        from src.preprocess import (
            COCOToYOLOConverter,
            DataSplitter,
            TrainAugmentor,
        )

        logger.info("=" * 50)
        logger.info("  PIPELINE DATASET — Surveillance-IA")
        logger.info("=" * 50)

        # 1. Filtrer les personnes (COCO)
        logger.info("\n[1/7] Filtrage catégorie « person »…")
        filtered_json = os.path.join(
            os.path.dirname(coco_json), "coco_people.json"
        )
        DatasetDownloader.filter_coco_people(coco_json, filtered_json)

        # 2. Conversion COCO → YOLO
        logger.info("\n[2/7] Conversion COCO → YOLO…")
        temp_labels = os.path.join(self.output_dir, "_temp_labels")
        converter = COCOToYOLOConverter()
        converter.convert(filtered_json, images_dir, temp_labels)

        # 3. Créer la structure
        logger.info("\n[3/7] Création structure YOLO…")
        self.builder.create_structure()

        # 4. Séparation Train/Val/Test
        logger.info("\n[4/7] Séparation 70/15/15…")
        splitter = DataSplitter()
        split_stats = splitter.split(
            images_dir, temp_labels, self.output_dir
        )

        # 5. Augmentation Train uniquement
        if augment_train and split_stats.get("train", 0) > 0:
            logger.info("\n[5/7] Augmentation Train…")
            augmentor = TrainAugmentor()
            augmentor.augment_directory(
                os.path.join(self.output_dir, "images", "train"),
                os.path.join(self.output_dir, "labels", "train"),
                num_augmented_per_image=num_augmentations,
            )
        else:
            logger.info("\n[5/7] Augmentation Train … SKIP")

        # 6. Générer data.yaml
        logger.info("\n[6/7] Génération data.yaml…")
        self.builder.generate_data_yaml()

        # 7. Vérification d'intégrité
        logger.info("\n[7/7] Vérification d'intégrité…")
        integrity = self.checker.check_all()

        # Nettoyage temp
        if os.path.exists(temp_labels):
            shutil.rmtree(temp_labels)

        # Stats finales
        self.builder.print_stats()

        return {
            "split_stats": split_stats,
            "integrity": integrity,
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Gestion du Dataset YOLO v8 — Surveillance-IA",
    )
    sub = parser.add_subparsers(dest="command")

    # ── create ──
    p_create = sub.add_parser("create", help="Créer la structure YOLO")
    p_create.add_argument("--root", default="data/splits")

    # ── yaml ──
    p_yaml = sub.add_parser("yaml", help="Générer data.yaml")
    p_yaml.add_argument("--root", default="data/splits")

    # ── stats ──
    p_stats = sub.add_parser("stats", help="Afficher les statistiques")
    p_stats.add_argument("--root", default="data/splits")

    # ── check ──
    p_check = sub.add_parser("check", help="Vérifier l'intégrité")
    p_check.add_argument("--root", default="data/splits")

    # ── datasets ──
    sub.add_parser("datasets", help="Lister les datasets supportés")

    # ── pipeline ──
    p_pipe = sub.add_parser("pipeline", help="Pipeline complète depuis COCO")
    p_pipe.add_argument("--coco-json", required=True)
    p_pipe.add_argument("--images-dir", required=True)
    p_pipe.add_argument("--output", default="data/splits")
    p_pipe.add_argument("--no-augment", action="store_true")

    args = parser.parse_args()

    if args.command == "create":
        builder = YOLODatasetBuilder(args.root)
        builder.create_structure()

    elif args.command == "yaml":
        builder = YOLODatasetBuilder(args.root)
        builder.generate_data_yaml()

    elif args.command == "stats":
        builder = YOLODatasetBuilder(args.root)
        builder.print_stats()

    elif args.command == "check":
        checker = DatasetIntegrityChecker(args.root)
        report = checker.check_all()
        print(json.dumps(report, indent=2, default=str))

    elif args.command == "datasets":
        DatasetDownloader.list_datasets()

    elif args.command == "pipeline":
        pipeline = DatasetPipeline(args.output)
        pipeline.prepare_from_coco(
            args.coco_json,
            args.images_dir,
            augment_train=not args.no_augment,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
