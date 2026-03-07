"""
═══════════════════════════════════════════════════════════════
MODULE 3 — Entraînement YOLO v8 (Fine-tuning)
═══════════════════════════════════════════════════════════════
- Fine-tuning yolov8m.pt (pré-entraîné COCO)
- Hyperparamètres :
    epochs=50, imgsz=640, batch=16, lr0=0.01,
    lrf=0.01, momentum=0.937, weight_decay=0.0005,
    patience=10 (early stopping)
- Callbacks de suivi + courbes d'apprentissage
- Compatible Google Colab (GPU T4)
═══════════════════════════════════════════════════════════════
"""

import os
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

import torch
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Constantes d'entraînement ──────────────────────────────────
DEFAULT_HYPERPARAMS = {
    "model": "yolov8m.pt",
    "epochs": 50,
    "imgsz": 640,
    "batch": 16,
    "lr0": 0.01,
    "lrf": 0.01,
    "momentum": 0.937,
    "weight_decay": 0.0005,
    "patience": 10,
    "optimizer": "SGD",
    "cos_lr": True,
    "warmup_epochs": 3,
    "warmup_momentum": 0.8,
    "warmup_bias_lr": 0.1,
    "box": 7.5,
    "cls": 0.5,
    "dfl": 1.5,
    "hsv_h": 0.015,
    "hsv_s": 0.7,
    "hsv_v": 0.4,
    "degrees": 0.0,
    "translate": 0.1,
    "scale": 0.5,
    "shear": 0.0,
    "perspective": 0.0,
    "flipud": 0.0,
    "fliplr": 0.5,
    "mosaic": 1.0,
    "mixup": 0.0,
    "copy_paste": 0.0,
}


# ═══════════════════════════════════════════════════════════════
# 1. TRAINER PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SurveillanceTrainer:
    """
    Entraîneur YOLO v8 fine-tuné pour la détection de personnes.

    Utilise le modèle pré-entraîné yolov8m.pt et affine
    sur notre dataset de surveillance pour atteindre ≥96% de précision.
    """

    def __init__(
        self,
        data_yaml: str = "data/splits/data.yaml",
        model_name: str = "yolov8m.pt",
        project_dir: str = "models/finetuned",
        experiment_name: Optional[str] = None,
    ):
        self.data_yaml = data_yaml
        self.model_name = model_name
        self.project_dir = project_dir
        self.experiment_name = experiment_name or datetime.now().strftime(
            "surv_%Y%m%d_%H%M%S"
        )

        # Vérifier CUDA
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1e9
            logger.info(f"🖥️  GPU détecté : {gpu_name} ({gpu_mem:.1f} GB)")
        else:
            logger.warning("⚠️ Pas de GPU — entraînement sur CPU (lent)")

        self.training_log = []

    def train(
        self,
        hyperparams: Optional[Dict] = None,
        resume: bool = False,
    ) -> Dict:
        """
        Lance le fine-tuning YOLO v8.

        Args:
            hyperparams: Hyperparamètres personnalisés (override defaults).
            resume: Reprendre un entraînement interrompu.

        Returns:
            Résultats de l'entraînement (métriques, chemin du modèle…).
        """
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "Ultralytics non installé. "
                "Exécuter : pip install ultralytics>=8.0.0"
            )

        # Fusionner les hyperparamètres
        params = {**DEFAULT_HYPERPARAMS}
        if hyperparams:
            params.update(hyperparams)

        # Vérifier que data.yaml existe
        if not os.path.exists(self.data_yaml):
            raise FileNotFoundError(
                f"data.yaml introuvable : {self.data_yaml}. "
                f"Exécuter d'abord : python -m src.dataset yaml"
            )

        logger.info("=" * 60)
        logger.info("  ENTRAÎNEMENT YOLO v8 — Surveillance-IA")
        logger.info("=" * 60)
        logger.info(f"  Modèle base  : {self.model_name}")
        logger.info(f"  Dataset      : {self.data_yaml}")
        logger.info(f"  Device       : {self.device}")
        logger.info(f"  Epochs       : {params['epochs']}")
        logger.info(f"  Batch size   : {params['batch']}")
        logger.info(f"  Image size   : {params['imgsz']}")
        logger.info(f"  Learning rate: {params['lr0']}")
        logger.info(f"  Patience     : {params['patience']}")
        logger.info("=" * 60)

        # Charger le modèle pré-entraîné
        model = YOLO(self.model_name)

        # Ajuster le batch size selon le GPU disponible
        if self.device == "cuda":
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1e9
            if gpu_mem < 8:  # GPU T4 (16GB) ou plus petit
                params["batch"] = min(params["batch"], 8)
                logger.info(
                    f"  Batch ajusté à {params['batch']} pour GPU {gpu_mem:.0f}GB"
                )

        start_time = time.time()

        # Enregistrer les callbacks
        self._register_callbacks(model)

        # Lancer l'entraînement
        results = model.train(
            data=self.data_yaml,
            epochs=params["epochs"],
            imgsz=params["imgsz"],
            batch=params["batch"],
            lr0=params["lr0"],
            lrf=params["lrf"],
            momentum=params["momentum"],
            weight_decay=params["weight_decay"],
            patience=params["patience"],
            optimizer=params["optimizer"],
            cos_lr=params["cos_lr"],
            warmup_epochs=params["warmup_epochs"],
            warmup_momentum=params["warmup_momentum"],
            warmup_bias_lr=params["warmup_bias_lr"],
            box=params["box"],
            cls=params["cls"],
            dfl=params["dfl"],
            hsv_h=params["hsv_h"],
            hsv_s=params["hsv_s"],
            hsv_v=params["hsv_v"],
            degrees=params["degrees"],
            translate=params["translate"],
            scale=params["scale"],
            shear=params["shear"],
            perspective=params["perspective"],
            flipud=params["flipud"],
            fliplr=params["fliplr"],
            mosaic=params["mosaic"],
            mixup=params["mixup"],
            copy_paste=params["copy_paste"],
            project=self.project_dir,
            name=self.experiment_name,
            device=self.device,
            workers=4 if self.device == "cuda" else 2,
            save=True,
            save_period=10,
            exist_ok=True,
            pretrained=True,
            verbose=True,
            seed=42,
            resume=resume,
        )

        elapsed = time.time() - start_time

        # Extraire les métriques finales
        output = self._extract_results(results, elapsed)

        # Sauvegarder le rapport
        self._save_training_report(output, params)

        logger.info("=" * 60)
        logger.info("  ENTRAÎNEMENT TERMINÉ")
        logger.info(f"  Durée       : {elapsed / 60:.1f} min")
        logger.info(f"  Best model  : {output.get('best_model_path', 'N/A')}")
        logger.info(f"  mAP@0.5     : {output.get('mAP50', 'N/A')}")
        logger.info(f"  Precision   : {output.get('precision', 'N/A')}")
        logger.info(f"  Recall      : {output.get('recall', 'N/A')}")
        logger.info("=" * 60)

        return output

    def _register_callbacks(self, model) -> None:
        """Enregistre les callbacks de suivi de l'entraînement."""

        def on_train_epoch_end(trainer):
            """Callback fin d'epoch — log des métriques."""
            epoch = trainer.epoch
            metrics = trainer.metrics or {}

            log_entry = {
                "epoch": epoch,
                "timestamp": datetime.now().isoformat(),
                "box_loss": metrics.get("train/box_loss", None),
                "cls_loss": metrics.get("train/cls_loss", None),
                "dfl_loss": metrics.get("train/dfl_loss", None),
                "precision": metrics.get("metrics/precision(B)", None),
                "recall": metrics.get("metrics/recall(B)", None),
                "mAP50": metrics.get("metrics/mAP50(B)", None),
                "mAP50_95": metrics.get("metrics/mAP50-95(B)", None),
                "lr": metrics.get("lr/pg0", None),
            }

            self.training_log.append(log_entry)

            if log_entry["mAP50"] is not None:
                logger.info(
                    f"  Epoch {epoch:3d} | "
                    f"mAP50={log_entry['mAP50']:.4f} | "
                    f"P={log_entry['precision']:.4f} | "
                    f"R={log_entry['recall']:.4f}"
                )

        model.add_callback("on_train_epoch_end", on_train_epoch_end)

    def _extract_results(self, results, elapsed: float) -> Dict:
        """Extrait les résultats de l'entraînement."""
        output = {
            "training_time_seconds": elapsed,
            "training_time_minutes": round(elapsed / 60, 2),
            "device": self.device,
            "training_log": self.training_log,
        }

        # Chercher le best model
        run_dir = Path(self.project_dir) / self.experiment_name
        best_path = run_dir / "weights" / "best.pt"
        last_path = run_dir / "weights" / "last.pt"

        if best_path.exists():
            output["best_model_path"] = str(best_path)
        if last_path.exists():
            output["last_model_path"] = str(last_path)

        # Métriques finales
        try:
            if hasattr(results, "results_dict"):
                res = results.results_dict
                output["precision"] = res.get("metrics/precision(B)", None)
                output["recall"] = res.get("metrics/recall(B)", None)
                output["mAP50"] = res.get("metrics/mAP50(B)", None)
                output["mAP50_95"] = res.get("metrics/mAP50-95(B)", None)
        except Exception as e:
            logger.warning(f"Impossible d'extraire les métriques finales : {e}")

        return output

    def _save_training_report(self, output: Dict, params: Dict) -> None:
        """Sauvegarde le rapport d'entraînement en JSON."""
        run_dir = Path(self.project_dir) / self.experiment_name
        os.makedirs(run_dir, exist_ok=True)

        report = {
            "experiment": self.experiment_name,
            "date": datetime.now().isoformat(),
            "hyperparameters": params,
            "results": output,
        }

        report_path = run_dir / "training_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"📄 Rapport sauvegardé : {report_path}")


# ═══════════════════════════════════════════════════════════════
# 2. ANALYSE DES COURBES D'APPRENTISSAGE
# ═══════════════════════════════════════════════════════════════

class TrainingAnalyzer:
    """
    Analyse et visualise les courbes d'apprentissage
    post-entraînement.
    """

    @staticmethod
    def plot_learning_curves(
        report_path: str,
        save_path: Optional[str] = None,
    ) -> None:
        """
        Trace les courbes de loss et métriques à partir du rapport JSON.

        Args:
            report_path: Chemin vers training_report.json
            save_path: Chemin pour sauvegarder le graphique.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib non installé")
            return

        with open(report_path, "r") as f:
            report = json.load(f)

        log = report.get("results", {}).get("training_log", [])
        if not log:
            logger.warning("Aucune donnée de log trouvée")
            return

        epochs = [e["epoch"] for e in log]
        mAP50 = [e.get("mAP50") for e in log]
        precision = [e.get("precision") for e in log]
        recall = [e.get("recall") for e in log]
        box_loss = [e.get("box_loss") for e in log]
        cls_loss = [e.get("cls_loss") for e in log]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            "Surveillance-IA — Courbes d'apprentissage",
            fontsize=16, fontweight="bold",
        )

        # mAP@0.5
        ax = axes[0, 0]
        if any(v is not None for v in mAP50):
            ax.plot(epochs, mAP50, "b-o", markersize=3, label="mAP@0.5")
            ax.axhline(y=0.96, color="r", linestyle="--", alpha=0.5, label="Cible 96%")
        ax.set_title("mAP@0.5")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("mAP")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Precision & Recall
        ax = axes[0, 1]
        if any(v is not None for v in precision):
            ax.plot(epochs, precision, "g-o", markersize=3, label="Precision")
        if any(v is not None for v in recall):
            ax.plot(epochs, recall, "orange", marker="o", markersize=3, label="Recall")
        ax.set_title("Precision & Recall")
        ax.set_xlabel("Epoch")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Box Loss
        ax = axes[1, 0]
        if any(v is not None for v in box_loss):
            ax.plot(epochs, box_loss, "r-o", markersize=3, label="Box Loss")
        ax.set_title("Box Loss")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Classification Loss
        ax = axes[1, 1]
        if any(v is not None for v in cls_loss):
            ax.plot(epochs, cls_loss, "m-o", markersize=3, label="Cls Loss")
        ax.set_title("Classification Loss")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            logger.info(f"📊 Courbes sauvegardées : {save_path}")
        else:
            plt.show()


# ═══════════════════════════════════════════════════════════════
# 3. GOOGLE COLAB HELPER
# ═══════════════════════════════════════════════════════════════

def generate_colab_notebook(output_path: str = "train_colab.py") -> None:
    """
    Génère un script compatible Google Colab pour l'entraînement.
    Adapté pour GPU T4 (free tier).
    """
    script = '''#!/usr/bin/env python3
"""
Surveillance-IA — Entraînement YOLO v8 sur Google Colab
GPU: T4 (free tier) — ~25 min pour 50 epochs

Étapes :
    1. Installer les dépendances
    2. Monter Google Drive (optionnel)
    3. Uploader le dataset
    4. Lancer l'entraînement
    5. Télécharger le modèle entraîné
"""

# ── Installation ──
# !pip install ultralytics>=8.0.0 torch torchvision

import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

from ultralytics import YOLO

# ── Configuration ──
DATA_YAML = "data/splits/data.yaml"  # Ajuster selon votre structure
MODEL_BASE = "yolov8m.pt"

# ── Entraînement ──
model = YOLO(MODEL_BASE)

results = model.train(
    data=DATA_YAML,
    epochs=50,
    imgsz=640,
    batch=16,
    lr0=0.01,
    lrf=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    patience=10,
    optimizer="SGD",
    cos_lr=True,
    device="cuda",
    workers=2,
    save=True,
    save_period=10,
    project="models/finetuned",
    name="colab_run",
    exist_ok=True,
    pretrained=True,
    verbose=True,
    seed=42,
)

print("\\n✅ Entraînement terminé !")
print(f"Best model: models/finetuned/colab_run/weights/best.pt")
'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script)

    logger.info(f"📓 Script Colab généré : {output_path}")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Entraînement YOLO v8 — Surveillance-IA",
    )
    sub = parser.add_subparsers(dest="command")

    # ── train ──
    p_train = sub.add_parser("train", help="Lancer l'entraînement")
    p_train.add_argument("--data", default="data/splits/data.yaml")
    p_train.add_argument("--model", default="yolov8m.pt")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--batch", type=int, default=16)
    p_train.add_argument("--imgsz", type=int, default=640)
    p_train.add_argument("--lr", type=float, default=0.01)
    p_train.add_argument("--patience", type=int, default=10)
    p_train.add_argument("--project", default="models/finetuned")
    p_train.add_argument("--name", default=None)
    p_train.add_argument("--resume", action="store_true")

    # ── plot ──
    p_plot = sub.add_parser("plot", help="Tracer les courbes d'apprentissage")
    p_plot.add_argument("--report", required=True, help="Chemin training_report.json")
    p_plot.add_argument("--save", default=None)

    # ── colab ──
    p_colab = sub.add_parser("colab", help="Générer script Colab")
    p_colab.add_argument("--output", default="train_colab.py")

    args = parser.parse_args()

    if args.command == "train":
        custom_params = {}
        if args.epochs != 50:
            custom_params["epochs"] = args.epochs
        if args.batch != 16:
            custom_params["batch"] = args.batch
        if args.imgsz != 640:
            custom_params["imgsz"] = args.imgsz
        if args.lr != 0.01:
            custom_params["lr0"] = args.lr
        if args.patience != 10:
            custom_params["patience"] = args.patience

        trainer = SurveillanceTrainer(
            data_yaml=args.data,
            model_name=args.model,
            project_dir=args.project,
            experiment_name=args.name,
        )
        trainer.train(
            hyperparams=custom_params if custom_params else None,
            resume=args.resume,
        )

    elif args.command == "plot":
        TrainingAnalyzer.plot_learning_curves(args.report, args.save)

    elif args.command == "colab":
        generate_colab_notebook(args.output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
