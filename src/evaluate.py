"""
═══════════════════════════════════════════════════════════════
MODULE 4 — Évaluation finale sur le Test set
═══════════════════════════════════════════════════════════════
- Évaluation UNE SEULE FOIS sur le set de Test
- Métriques : mAP@0.5, mAP@0.5:0.95, Precision, Recall, F1
- Mesure du FPS (inférence)
- Cible : ≥96% de précision
- Matrice de confusion + courbe PR
═══════════════════════════════════════════════════════════════
"""

import os
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

import torch
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Cible SAHELYS ──────────────────────────────────────────────
TARGET_PRECISION = 0.96  # ≥96%


# ═══════════════════════════════════════════════════════════════
# 1. ÉVALUATEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SurveillanceEvaluator:
    """
    Évaluation finale du modèle YOLO v8 fine-tuné.

    ⚠️ RÈGLE : le Test set ne doit être évalué qu'UNE SEULE FOIS,
    après la fin de l'entraînement. Aucun ajustement d'hyperparamètres
    ne doit être fait suite à cette évaluation.
    """

    def __init__(
        self,
        model_path: str,
        data_yaml: str = "data/splits/data.yaml",
    ):
        """
        Args:
            model_path: Chemin vers best.pt (modèle entraîné).
            data_yaml: Chemin vers data.yaml du dataset.
        """
        self.model_path = model_path
        self.data_yaml = data_yaml
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Vérifications
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modèle introuvable : {model_path}")
        if not os.path.exists(data_yaml):
            raise FileNotFoundError(f"data.yaml introuvable : {data_yaml}")

    def evaluate(
        self,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.5,
        save_dir: Optional[str] = None,
    ) -> Dict:
        """
        Lance l'évaluation complète sur le Test set.

        ⚠️ APPELER UNE SEULE FOIS.

        Args:
            conf_threshold: Seuil de confiance pour les détections.
            iou_threshold: Seuil IoU pour le matching GT/pred.
            save_dir: Dossier de sauvegarde des résultats.

        Returns:
            Dict avec toutes les métriques d'évaluation.
        """
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("ultralytics non installé")

        logger.info("=" * 60)
        logger.info("  ÉVALUATION FINALE — Test Set (UNIQUE)")
        logger.info("=" * 60)
        logger.info(f"  Modèle  : {self.model_path}")
        logger.info(f"  Dataset : {self.data_yaml}")
        logger.info(f"  Device  : {self.device}")
        logger.info(f"  Conf    : {conf_threshold}")
        logger.info(f"  IoU     : {iou_threshold}")
        logger.info("=" * 60)

        # Charger le modèle
        model = YOLO(self.model_path)

        # Évaluation sur le split test
        results = model.val(
            data=self.data_yaml,
            split="test",
            conf=conf_threshold,
            iou=iou_threshold,
            device=self.device,
            verbose=True,
            save_json=True,
            plots=True,
        )

        # Extraire les métriques
        metrics = self._extract_metrics(results)

        # Mesurer le FPS
        fps_metrics = self._measure_fps(model)
        metrics.update(fps_metrics)

        # Vérifier la cible
        metrics["target_precision"] = TARGET_PRECISION
        precision = metrics.get("precision", 0)
        metrics["target_reached"] = precision >= TARGET_PRECISION

        if metrics["target_reached"]:
            logger.info(
                f"  ✅ CIBLE ATTEINTE : Precision = {precision:.4f} "
                f"(≥ {TARGET_PRECISION})"
            )
        else:
            logger.warning(
                f"  ⚠️ CIBLE NON ATTEINTE : Precision = {precision:.4f} "
                f"(< {TARGET_PRECISION})"
            )

        # Sauvegarder le rapport
        if save_dir:
            self._save_evaluation_report(metrics, save_dir)

        self._print_results(metrics)

        return metrics

    def _extract_metrics(self, results) -> Dict:
        """Extrait les métriques depuis les résultats YOLO."""
        metrics = {
            "evaluation_date": datetime.now().isoformat(),
            "model_path": self.model_path,
            "device": self.device,
        }

        try:
            # Métriques de base
            if hasattr(results, "results_dict"):
                rd = results.results_dict
                metrics["precision"] = rd.get("metrics/precision(B)", 0)
                metrics["recall"] = rd.get("metrics/recall(B)", 0)
                metrics["mAP50"] = rd.get("metrics/mAP50(B)", 0)
                metrics["mAP50_95"] = rd.get("metrics/mAP50-95(B)", 0)
                metrics["fitness"] = rd.get("fitness", 0)

            # F1 score
            p = metrics.get("precision", 0)
            r = metrics.get("recall", 0)
            if p + r > 0:
                metrics["f1_score"] = 2 * p * r / (p + r)
            else:
                metrics["f1_score"] = 0.0

            # Métriques par classe (si disponibles)
            if hasattr(results, "box"):
                box = results.box
                if hasattr(box, "ap50"):
                    metrics["ap50_per_class"] = box.ap50.tolist()
                if hasattr(box, "ap"):
                    metrics["ap_per_class"] = box.ap.tolist()

            # Nombre d'images testées
            if hasattr(results, "speed"):
                speed = results.speed
                metrics["speed"] = {
                    "preprocess_ms": speed.get("preprocess", 0),
                    "inference_ms": speed.get("inference", 0),
                    "postprocess_ms": speed.get("postprocess", 0),
                }

        except Exception as e:
            logger.warning(f"Erreur extraction métriques : {e}")

        return metrics

    def _measure_fps(
        self,
        model,
        num_iterations: int = 100,
        imgsz: int = 640,
    ) -> Dict:
        """
        Mesure le FPS d'inférence sur des images synthétiques.

        Returns:
            {fps: float, avg_inference_ms: float}
        """
        logger.info("  Mesure du FPS…")

        # Image synthétique
        dummy_img = np.random.randint(
            0, 255, (imgsz, imgsz, 3), dtype=np.uint8
        )

        # Warmup
        for _ in range(10):
            model.predict(dummy_img, verbose=False)

        # Benchmark
        start = time.time()
        for _ in range(num_iterations):
            model.predict(dummy_img, verbose=False)
        elapsed = time.time() - start

        fps = num_iterations / elapsed
        avg_ms = (elapsed / num_iterations) * 1000

        logger.info(f"  FPS: {fps:.1f} | Latence: {avg_ms:.1f}ms")

        return {
            "fps": round(fps, 2),
            "avg_inference_ms": round(avg_ms, 2),
            "benchmark_iterations": num_iterations,
        }

    def _save_evaluation_report(self, metrics: Dict, save_dir: str) -> None:
        """Sauvegarde le rapport d'évaluation complet."""
        os.makedirs(save_dir, exist_ok=True)

        report_path = os.path.join(save_dir, "evaluation_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"📄 Rapport d'évaluation sauvegardé : {report_path}")

    def _print_results(self, metrics: Dict) -> None:
        """Affiche les résultats d'évaluation formatés."""
        print("\n" + "=" * 60)
        print("  RÉSULTATS D'ÉVALUATION — Surveillance-IA")
        print("=" * 60)
        print(f"  Precision        : {metrics.get('precision', 0):.4f}")
        print(f"  Recall           : {metrics.get('recall', 0):.4f}")
        print(f"  F1 Score         : {metrics.get('f1_score', 0):.4f}")
        print(f"  mAP@0.5          : {metrics.get('mAP50', 0):.4f}")
        print(f"  mAP@0.5:0.95     : {metrics.get('mAP50_95', 0):.4f}")
        print(f"  FPS              : {metrics.get('fps', 0):.1f}")
        print(f"  Latence (ms)     : {metrics.get('avg_inference_ms', 0):.1f}")
        print("-" * 60)
        target_status = "✅ OUI" if metrics.get("target_reached") else "❌ NON"
        print(f"  Cible ≥96%       : {target_status}")
        print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════
# 2. COMPARAISON DE MODÈLES
# ═══════════════════════════════════════════════════════════════

class ModelComparator:
    """Compare les performances de plusieurs modèles."""

    @staticmethod
    def compare(
        model_paths: List[str],
        data_yaml: str,
        save_path: Optional[str] = None,
    ) -> List[Dict]:
        """
        Évalue et compare plusieurs modèles sur le même Test set.

        Returns:
            Liste de métriques par modèle, triée par mAP@0.5.
        """
        results = []

        for model_path in model_paths:
            logger.info(f"\nÉvaluation : {model_path}")
            try:
                evaluator = SurveillanceEvaluator(model_path, data_yaml)
                metrics = evaluator.evaluate()
                metrics["model_name"] = Path(model_path).parent.name
                results.append(metrics)
            except Exception as e:
                logger.error(f"Erreur pour {model_path}: {e}")

        # Trier par mAP@0.5 décroissant
        results.sort(key=lambda x: x.get("mAP50", 0), reverse=True)

        # Afficher le résumé
        print("\n" + "=" * 70)
        print("  COMPARAISON DES MODÈLES")
        print("=" * 70)
        print(
            f"  {'Modèle':<25} {'Precision':<12} {'Recall':<10} "
            f"{'mAP50':<10} {'FPS':<8}"
        )
        print("-" * 70)
        for r in results:
            print(
                f"  {r.get('model_name', '?'):<25} "
                f"{r.get('precision', 0):<12.4f} "
                f"{r.get('recall', 0):<10.4f} "
                f"{r.get('mAP50', 0):<10.4f} "
                f"{r.get('fps', 0):<8.1f}"
            )
        print("=" * 70 + "\n")

        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"📄 Comparaison sauvegardée : {save_path}")

        return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Évaluation YOLO v8 — Surveillance-IA",
    )
    sub = parser.add_subparsers(dest="command")

    # ── evaluate ──
    p_eval = sub.add_parser("evaluate", help="Évaluer sur le Test set (UNE FOIS)")
    p_eval.add_argument("--model", required=True, help="Chemin vers best.pt")
    p_eval.add_argument("--data", default="data/splits/data.yaml")
    p_eval.add_argument("--conf", type=float, default=0.25)
    p_eval.add_argument("--iou", type=float, default=0.5)
    p_eval.add_argument("--save-dir", default="models/finetuned/evaluation")

    # ── compare ──
    p_compare = sub.add_parser("compare", help="Comparer plusieurs modèles")
    p_compare.add_argument("--models", nargs="+", required=True)
    p_compare.add_argument("--data", default="data/splits/data.yaml")
    p_compare.add_argument("--save", default="models/finetuned/comparison.json")

    args = parser.parse_args()

    if args.command == "evaluate":
        evaluator = SurveillanceEvaluator(args.model, args.data)
        evaluator.evaluate(
            conf_threshold=args.conf,
            iou_threshold=args.iou,
            save_dir=args.save_dir,
        )

    elif args.command == "compare":
        ModelComparator.compare(
            args.models, args.data, args.save
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
