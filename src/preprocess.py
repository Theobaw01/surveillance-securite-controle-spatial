"""
═══════════════════════════════════════════════════════════════
MODULE 1 — Prétraitement vidéo & annotations
═══════════════════════════════════════════════════════════════
- Extraction de frames depuis vidéos à 5 FPS
- Conversion annotations COCO → format YOLO
- Vérification qualité des annotations
- Data augmentation sur Train uniquement
- Séparation 70% Train / 15% Val / 15% Test
═══════════════════════════════════════════════════════════════
"""

import os
import cv2
import json
import shutil
import random
import logging
import argparse
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────
TARGET_FPS = 5
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
PERSON_CLASS_ID = 0  # Classe « person » en YOLO
COCO_PERSON_CAT_ID = 1  # ID catégorie « person » dans COCO


# ═══════════════════════════════════════════════════════════════
# 1. EXTRACTION DE FRAMES
# ═══════════════════════════════════════════════════════════════

class FrameExtractor:
    """
    Extrait des frames depuis une vidéo à un FPS cible
    pour éviter la redondance (5 FPS par défaut).
    """

    def __init__(self, target_fps: int = TARGET_FPS):
        self.target_fps = target_fps

    def extract(
        self,
        video_path: str,
        output_dir: str,
        prefix: str = "",
    ) -> List[str]:
        """
        Extrait les frames d'une vidéo.

        Args:
            video_path: Chemin vers la vidéo source.
            output_dir: Dossier de sortie pour les frames.
            prefix: Préfixe ajouté aux noms de fichiers.

        Returns:
            Liste des chemins des frames sauvegardées.
        """
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Impossible d'ouvrir la vidéo : {video_path}")

        src_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(1, int(round(src_fps / self.target_fps)))

        logger.info(
            f"Vidéo : {video_path} | {src_fps:.1f} FPS | "
            f"{total_frames} frames | intervalle={frame_interval}"
        )

        saved_paths = []
        frame_idx = 0
        saved_count = 0

        with tqdm(total=total_frames, desc="Extraction frames") as pbar:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_interval == 0:
                    filename = f"{prefix}{saved_count:06d}.jpg"
                    filepath = os.path.join(output_dir, filename)
                    cv2.imwrite(filepath, frame)
                    saved_paths.append(filepath)
                    saved_count += 1

                frame_idx += 1
                pbar.update(1)

        cap.release()
        logger.info(f"✅ {saved_count} frames extraites → {output_dir}")
        return saved_paths

    def extract_batch(
        self,
        video_dir: str,
        output_dir: str,
    ) -> List[str]:
        """Extrait les frames de toutes les vidéos d'un dossier."""
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}
        all_paths = []

        video_files = [
            f for f in Path(video_dir).iterdir()
            if f.suffix.lower() in video_extensions
        ]

        if not video_files:
            logger.warning(f"Aucune vidéo trouvée dans {video_dir}")
            return all_paths

        for video_file in video_files:
            prefix = f"{video_file.stem}_"
            paths = self.extract(str(video_file), output_dir, prefix)
            all_paths.extend(paths)

        logger.info(f"✅ Total : {len(all_paths)} frames extraites")
        return all_paths


# ═══════════════════════════════════════════════════════════════
# 2. CONVERSION ANNOTATIONS COCO → YOLO
# ═══════════════════════════════════════════════════════════════

class COCOToYOLOConverter:
    """
    Convertit les annotations au format COCO JSON
    vers le format YOLO (un fichier .txt par image).

    Format YOLO : <class_id> <x_center> <y_center> <width> <height>
    Toutes les valeurs sont normalisées [0, 1].
    """

    def __init__(self, target_classes: Optional[List[int]] = None):
        """
        Args:
            target_classes: IDs des catégories COCO à conserver.
                           Par défaut [1] = person uniquement.
        """
        self.target_classes = target_classes or [COCO_PERSON_CAT_ID]

    def convert(
        self,
        coco_json_path: str,
        images_dir: str,
        output_labels_dir: str,
    ) -> Dict[str, int]:
        """
        Convertit un fichier annotations COCO JSON entier.

        Returns:
            Stats de conversion {images_traitées, annotations_converties, ...}
        """
        os.makedirs(output_labels_dir, exist_ok=True)

        with open(coco_json_path, "r", encoding="utf-8") as f:
            coco_data = json.load(f)

        # Mapper category_id COCO → class_id YOLO (0-indexed)
        cat_mapping = {}
        for idx, cat_id in enumerate(self.target_classes):
            cat_mapping[cat_id] = idx

        # Index images par ID
        image_info = {}
        for img in coco_data.get("images", []):
            image_info[img["id"]] = {
                "file_name": img["file_name"],
                "width": img["width"],
                "height": img["height"],
            }

        # Regrouper annotations par image_id
        annotations_by_image = {}
        for ann in coco_data.get("annotations", []):
            if ann["category_id"] not in cat_mapping:
                continue
            img_id = ann["image_id"]
            if img_id not in annotations_by_image:
                annotations_by_image[img_id] = []
            annotations_by_image[img_id].append(ann)

        stats = {
            "images_processed": 0,
            "annotations_converted": 0,
            "images_skipped": 0,
        }

        for img_id, img_data in tqdm(
            image_info.items(), desc="Conversion COCO → YOLO"
        ):
            img_w = img_data["width"]
            img_h = img_data["height"]
            img_name = Path(img_data["file_name"]).stem

            anns = annotations_by_image.get(img_id, [])
            if not anns:
                stats["images_skipped"] += 1
                continue

            label_path = os.path.join(output_labels_dir, f"{img_name}.txt")
            yolo_lines = []

            for ann in anns:
                bbox = ann["bbox"]  # COCO: [x_min, y_min, width, height]
                class_id = cat_mapping[ann["category_id"]]

                # Conversion COCO → YOLO (normalisé, centré)
                x_center = (bbox[0] + bbox[2] / 2.0) / img_w
                y_center = (bbox[1] + bbox[3] / 2.0) / img_h
                w = bbox[2] / img_w
                h = bbox[3] / img_h

                # Clipper dans [0, 1]
                x_center = max(0.0, min(1.0, x_center))
                y_center = max(0.0, min(1.0, y_center))
                w = max(0.0, min(1.0, w))
                h = max(0.0, min(1.0, h))

                if w > 0.001 and h > 0.001:
                    yolo_lines.append(
                        f"{class_id} {x_center:.6f} {y_center:.6f} "
                        f"{w:.6f} {h:.6f}"
                    )
                    stats["annotations_converted"] += 1

            if yolo_lines:
                with open(label_path, "w") as f:
                    f.write("\n".join(yolo_lines) + "\n")
                stats["images_processed"] += 1

        logger.info(
            f"✅ Conversion terminée : {stats['images_processed']} images, "
            f"{stats['annotations_converted']} annotations"
        )
        return stats


# ═══════════════════════════════════════════════════════════════
# 3. VÉRIFICATION QUALITÉ DES ANNOTATIONS
# ═══════════════════════════════════════════════════════════════

class AnnotationValidator:
    """Vérifie l'intégrité et la qualité des annotations YOLO."""

    def __init__(
        self,
        min_bbox_area: float = 0.0005,
        max_bbox_area: float = 0.95,
    ):
        self.min_bbox_area = min_bbox_area
        self.max_bbox_area = max_bbox_area

    def validate(
        self,
        images_dir: str,
        labels_dir: str,
    ) -> Dict[str, any]:
        """
        Vérifie la cohérence images ↔ labels.

        Returns:
            Rapport de validation.
        """
        img_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
        images = {
            Path(f).stem
            for f in os.listdir(images_dir)
            if Path(f).suffix.lower() in img_extensions
        }
        labels = {
            Path(f).stem
            for f in os.listdir(labels_dir)
            if f.endswith(".txt")
        }

        missing_labels = images - labels
        orphan_labels = labels - images
        matched = images & labels

        issues = []
        total_bboxes = 0
        invalid_bboxes = 0

        for stem in tqdm(matched, desc="Validation annotations"):
            label_path = os.path.join(labels_dir, f"{stem}.txt")
            with open(label_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    parts = line.strip().split()
                    if len(parts) != 5:
                        issues.append(
                            f"{stem}.txt L{line_num}: format invalide "
                            f"({len(parts)} champs au lieu de 5)"
                        )
                        continue

                    total_bboxes += 1
                    try:
                        cls_id = int(parts[0])
                        xc, yc, w, h = [float(v) for v in parts[1:]]
                    except ValueError:
                        issues.append(
                            f"{stem}.txt L{line_num}: valeur non numérique"
                        )
                        invalid_bboxes += 1
                        continue

                    # Vérifier bornes
                    for val, name in [(xc, "xc"), (yc, "yc"), (w, "w"), (h, "h")]:
                        if val < 0 or val > 1:
                            issues.append(
                                f"{stem}.txt L{line_num}: {name}={val:.4f} hors [0,1]"
                            )
                            invalid_bboxes += 1
                            break

                    area = w * h
                    if area < self.min_bbox_area:
                        issues.append(
                            f"{stem}.txt L{line_num}: bbox trop petite "
                            f"(area={area:.6f})"
                        )
                        invalid_bboxes += 1
                    elif area > self.max_bbox_area:
                        issues.append(
                            f"{stem}.txt L{line_num}: bbox trop grande "
                            f"(area={area:.4f})"
                        )
                        invalid_bboxes += 1

        report = {
            "total_images": len(images),
            "total_labels": len(labels),
            "matched_pairs": len(matched),
            "missing_labels": len(missing_labels),
            "orphan_labels": len(orphan_labels),
            "total_bboxes": total_bboxes,
            "invalid_bboxes": invalid_bboxes,
            "valid_bboxes": total_bboxes - invalid_bboxes,
            "issues_count": len(issues),
            "issues": issues[:50],  # Limiter l'affichage
        }

        logger.info(
            f"✅ Validation : {matched} paires OK | "
            f"{invalid_bboxes}/{total_bboxes} bbox invalides | "
            f"{len(issues)} problèmes détectés"
        )
        return report


# ═══════════════════════════════════════════════════════════════
# 4. DATA AUGMENTATION (Train uniquement)
# ═══════════════════════════════════════════════════════════════

class TrainAugmentor:
    """
    Data augmentation pour le set d'entraînement UNIQUEMENT.
    ⚠️ JAMAIS appliqué sur Val ou Test.

    Augmentations :
    - Flip horizontal
    - Variations luminosité / contraste
    - Bruit gaussien
    - Mosaic (natif YOLO v8, activé dans train.py)
    """

    def __init__(
        self,
        flip_prob: float = 0.5,
        brightness_range: Tuple[float, float] = (0.7, 1.3),
        contrast_range: Tuple[float, float] = (0.7, 1.3),
        noise_std: float = 10.0,
        noise_prob: float = 0.3,
    ):
        self.flip_prob = flip_prob
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.noise_std = noise_std
        self.noise_prob = noise_prob

    def augment(
        self,
        image: np.ndarray,
        labels: List[str],
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Applique des augmentations aléatoires.

        Args:
            image: Image BGR (OpenCV).
            labels: Lignes d'annotations YOLO.

        Returns:
            (image_augmentée, labels_mis_à_jour)
        """
        aug_image = image.copy()
        aug_labels = list(labels)

        # Flip horizontal
        if random.random() < self.flip_prob:
            aug_image = cv2.flip(aug_image, 1)
            aug_labels = self._flip_labels_horizontal(aug_labels)

        # Variation de luminosité
        factor = random.uniform(*self.brightness_range)
        aug_image = np.clip(aug_image * factor, 0, 255).astype(np.uint8)

        # Variation de contraste
        contrast = random.uniform(*self.contrast_range)
        mean = np.mean(aug_image)
        aug_image = np.clip(
            (aug_image.astype(np.float32) - mean) * contrast + mean,
            0, 255,
        ).astype(np.uint8)

        # Bruit gaussien
        if random.random() < self.noise_prob:
            noise = np.random.normal(0, self.noise_std, aug_image.shape)
            aug_image = np.clip(
                aug_image.astype(np.float32) + noise, 0, 255
            ).astype(np.uint8)

        return aug_image, aug_labels

    @staticmethod
    def _flip_labels_horizontal(labels: List[str]) -> List[str]:
        """Ajuste les coordonnées YOLO après flip horizontal."""
        flipped = []
        for line in labels:
            parts = line.strip().split()
            if len(parts) == 5:
                cls_id = parts[0]
                xc = 1.0 - float(parts[1])
                yc = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])
                flipped.append(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
        return flipped

    def augment_directory(
        self,
        images_dir: str,
        labels_dir: str,
        num_augmented_per_image: int = 2,
    ) -> int:
        """
        Augmente toutes les images d'un dossier Train.

        Returns:
            Nombre d'images augmentées créées.
        """
        img_extensions = {".jpg", ".jpeg", ".png"}
        image_files = [
            f for f in os.listdir(images_dir)
            if Path(f).suffix.lower() in img_extensions
        ]

        count = 0
        for img_file in tqdm(image_files, desc="Augmentation Train"):
            img_path = os.path.join(images_dir, img_file)
            label_file = Path(img_file).stem + ".txt"
            label_path = os.path.join(labels_dir, label_file)

            if not os.path.exists(label_path):
                continue

            image = cv2.imread(img_path)
            if image is None:
                continue

            with open(label_path, "r") as f:
                labels = f.readlines()

            for i in range(num_augmented_per_image):
                aug_img, aug_labels = self.augment(image, labels)

                # Sauvegarder l'image augmentée
                aug_name = f"{Path(img_file).stem}_aug{i}{Path(img_file).suffix}"
                cv2.imwrite(os.path.join(images_dir, aug_name), aug_img)

                # Sauvegarder les labels augmentés
                aug_label_name = f"{Path(img_file).stem}_aug{i}.txt"
                with open(os.path.join(labels_dir, aug_label_name), "w") as f:
                    f.write("\n".join(aug_labels) + "\n")

                count += 1

        logger.info(f"✅ {count} images augmentées créées")
        return count


# ═══════════════════════════════════════════════════════════════
# 5. SÉPARATION TRAIN / VAL / TEST
# ═══════════════════════════════════════════════════════════════

class DataSplitter:
    """
    Sépare le dataset en Train(70%) / Val(15%) / Test(15%).

    ⚠️ RÈGLES :
    - Mélange aléatoire avec seed fixe (reproductibilité)
    - fit_transform() sur Train uniquement
    - Le Test set ne sera évalué qu'UNE SEULE FOIS
    """

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
    ):
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, \
            "Les ratios doivent sommer à 1.0"
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.seed = seed

    def split(
        self,
        images_dir: str,
        labels_dir: str,
        output_base_dir: str,
    ) -> Dict[str, int]:
        """
        Effectue la séparation et copie les fichiers.

        Structure de sortie :
            output_base_dir/
            ├── images/
            │   ├── train/
            │   ├── val/
            │   └── test/
            └── labels/
                ├── train/
                ├── val/
                └── test/

        Returns:
            Nombre de fichiers par split.
        """
        # Lister les paires image+label existantes
        img_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
        image_files = [
            f for f in os.listdir(images_dir)
            if Path(f).suffix.lower() in img_extensions
        ]

        # Ne garder que celles qui ont un label correspondant
        valid_pairs = []
        for img_file in image_files:
            label_file = Path(img_file).stem + ".txt"
            if os.path.exists(os.path.join(labels_dir, label_file)):
                valid_pairs.append((img_file, label_file))

        if not valid_pairs:
            logger.error("Aucune paire image/label trouvée !")
            return {}

        # Mélange avec seed fixe pour reproductibilité
        random.seed(self.seed)
        random.shuffle(valid_pairs)

        n = len(valid_pairs)
        train_end = int(n * self.train_ratio)
        val_end = int(n * (self.train_ratio + self.val_ratio))

        splits = {
            "train": valid_pairs[:train_end],
            "val": valid_pairs[train_end:val_end],
            "test": valid_pairs[val_end:],
        }

        stats = {}
        for split_name, pairs in splits.items():
            img_out = os.path.join(output_base_dir, "images", split_name)
            lbl_out = os.path.join(output_base_dir, "labels", split_name)
            os.makedirs(img_out, exist_ok=True)
            os.makedirs(lbl_out, exist_ok=True)

            for img_file, label_file in pairs:
                shutil.copy2(
                    os.path.join(images_dir, img_file),
                    os.path.join(img_out, img_file),
                )
                shutil.copy2(
                    os.path.join(labels_dir, label_file),
                    os.path.join(lbl_out, label_file),
                )

            stats[split_name] = len(pairs)
            logger.info(f"  {split_name}: {len(pairs)} images")

        logger.info(
            f"✅ Séparation terminée : "
            f"Train={stats['train']} | Val={stats['val']} | Test={stats['test']}"
        )
        return stats


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Prétraitement vidéo + annotations pour Surveillance-IA",
    )
    sub = parser.add_subparsers(dest="command")

    # ── extract ──
    p_extract = sub.add_parser("extract", help="Extraire les frames d'une vidéo")
    p_extract.add_argument("--video", required=True, help="Chemin vidéo ou dossier")
    p_extract.add_argument("--output", default="data/processed/frames")
    p_extract.add_argument("--fps", type=int, default=TARGET_FPS)

    # ── convert ──
    p_convert = sub.add_parser("convert", help="Convertir annotations COCO → YOLO")
    p_convert.add_argument("--coco-json", required=True)
    p_convert.add_argument("--images-dir", required=True)
    p_convert.add_argument("--output", default="data/processed/labels")

    # ── validate ──
    p_val = sub.add_parser("validate", help="Vérifier les annotations")
    p_val.add_argument("--images-dir", required=True)
    p_val.add_argument("--labels-dir", required=True)

    # ── split ──
    p_split = sub.add_parser("split", help="Séparer Train/Val/Test")
    p_split.add_argument("--images-dir", required=True)
    p_split.add_argument("--labels-dir", required=True)
    p_split.add_argument("--output", default="data/splits")

    # ── augment ──
    p_aug = sub.add_parser("augment", help="Augmenter le Train set")
    p_aug.add_argument("--images-dir", required=True)
    p_aug.add_argument("--labels-dir", required=True)
    p_aug.add_argument("--num-aug", type=int, default=2)

    args = parser.parse_args()

    if args.command == "extract":
        extractor = FrameExtractor(target_fps=args.fps)
        if os.path.isdir(args.video):
            extractor.extract_batch(args.video, args.output)
        else:
            extractor.extract(args.video, args.output)

    elif args.command == "convert":
        converter = COCOToYOLOConverter(target_classes=[COCO_PERSON_CAT_ID])
        converter.convert(args.coco_json, args.images_dir, args.output)

    elif args.command == "validate":
        validator = AnnotationValidator()
        report = validator.validate(args.images_dir, args.labels_dir)
        print(json.dumps(report, indent=2, default=str))

    elif args.command == "split":
        splitter = DataSplitter()
        splitter.split(args.images_dir, args.labels_dir, args.output)

    elif args.command == "augment":
        augmentor = TrainAugmentor()
        augmentor.augment_directory(
            args.images_dir, args.labels_dir, args.num_aug
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
