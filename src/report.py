"""
═══════════════════════════════════════════════════════════════
MODULE 10b — Génération de rapports PDF (ReportLab)
═══════════════════════════════════════════════════════════════
- Rapport quotidien PDF complet
- Statistiques + graphiques (matplotlib)
- Génération automatique
- Compatible avec l'API /report/{date}
═══════════════════════════════════════════════════════════════
"""

import os
import io
import logging
import argparse
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. GÉNÉRATEUR DE RAPPORTS PDF
# ═══════════════════════════════════════════════════════════════

class SurveillanceReportGenerator:
    """
    Génère des rapports PDF quotidiens complets pour Surveillance-IA.

    Contenu :
    - En-tête avec logo et date
    - Résumé des métriques clés
    - Graphiques (histogramme horaire, courbe d'occupation)
    - Tableau des événements
    - Alertes du jour
    - Pied de page
    """

    def __init__(
        self,
        output_dir: str = "reports",
        company_name: str = "SAHELYS",
        project_name: str = "Surveillance-IA",
    ):
        self.output_dir = output_dir
        self.company_name = company_name
        self.project_name = project_name
        os.makedirs(output_dir, exist_ok=True)

    def generate_daily_report(
        self,
        report_date: date,
        stats: Dict,
        events: List[Dict],
        alerts: List[Dict],
        save_path: Optional[str] = None,
    ) -> str:
        """
        Génère le rapport PDF quotidien.

        Args:
            report_date: Date du rapport.
            stats: Statistiques (entrées, sorties, occupation…).
            events: Liste des événements de passage.
            alerts: Liste des alertes.
            save_path: Chemin de sortie (auto-généré si None).

        Returns:
            Chemin du fichier PDF généré.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm, mm
            from reportlab.lib.colors import HexColor, black, white
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import (
                SimpleDocTemplate,
                Paragraph,
                Spacer,
                Table,
                TableStyle,
                Image,
                PageBreak,
            )
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        except ImportError:
            raise ImportError(
                "reportlab non installé. "
                "Exécuter : pip install reportlab>=4.0.0"
            )

        if save_path is None:
            save_path = os.path.join(
                self.output_dir,
                f"rapport_{report_date.isoformat()}.pdf",
            )

        # Créer le document
        doc = SimpleDocTemplate(
            save_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontSize=24,
            textColor=HexColor("#1a237e"),
            spaceAfter=20,
            alignment=TA_CENTER,
        )
        subtitle_style = ParagraphStyle(
            "CustomSubtitle",
            parent=styles["Heading2"],
            fontSize=16,
            textColor=HexColor("#283593"),
            spaceBefore=15,
            spaceAfter=10,
        )
        body_style = ParagraphStyle(
            "CustomBody",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
        )
        metric_style = ParagraphStyle(
            "MetricStyle",
            parent=styles["Normal"],
            fontSize=14,
            textColor=HexColor("#1565c0"),
            alignment=TA_CENTER,
        )

        # Éléments du document
        elements = []

        # ─── EN-TÊTE ────────────────────────────────────────────
        elements.append(Paragraph(
            f"🎥 {self.project_name}",
            title_style,
        ))
        elements.append(Paragraph(
            f"Rapport Quotidien — {report_date.strftime('%A %d %B %Y')}",
            ParagraphStyle(
                "DateStyle",
                parent=styles["Normal"],
                fontSize=14,
                alignment=TA_CENTER,
                textColor=HexColor("#546e7a"),
            ),
        ))
        elements.append(Paragraph(
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} | "
            f"{self.company_name}",
            ParagraphStyle(
                "GenStyle",
                parent=styles["Normal"],
                fontSize=10,
                alignment=TA_CENTER,
                textColor=HexColor("#9e9e9e"),
            ),
        ))
        elements.append(Spacer(1, 20))

        # ─── RÉSUMÉ ─────────────────────────────────────────────
        elements.append(Paragraph("📊 Résumé des métriques", subtitle_style))

        total_entries = stats.get("total_entries", 0)
        total_exits = stats.get("total_exits", 0)
        peak = stats.get("peak_occupancy", 0)
        unique = stats.get("total_unique_persons", 0)
        avg_time = stats.get("avg_presence_time", 0)
        total_alerts = stats.get("total_alerts", 0)

        metrics_data = [
            ["Métrique", "Valeur"],
            ["Total Entrées", str(total_entries)],
            ["Total Sorties", str(total_exits)],
            ["Occupation Max", str(peak)],
            ["Personnes Uniques", str(unique)],
            ["Temps Moyen (min)", f"{avg_time / 60:.1f}"],
            ["Alertes", str(total_alerts)],
        ]

        metrics_table = Table(
            metrics_data,
            colWidths=[8 * cm, 5 * cm],
        )
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1a237e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("FONTSIZE", (0, 1), (-1, -1), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#e8eaf6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                HexColor("#e8eaf6"), HexColor("#c5cae9"),
            ]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#9e9e9e")),
            ("TOPPADDING", (0, 1), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 20))

        # ─── GRAPHIQUES ─────────────────────────────────────────
        elements.append(Paragraph("📈 Analyse graphique", subtitle_style))

        chart_path = self._generate_charts(report_date, stats, events)
        if chart_path and os.path.exists(chart_path):
            elements.append(Image(chart_path, width=16 * cm, height=10 * cm))
            elements.append(Spacer(1, 15))

        # ─── ÉVÉNEMENTS ─────────────────────────────────────────
        if events:
            elements.append(Paragraph(
                f"📋 Événements ({len(events)} passages)", subtitle_style,
            ))

            # Limiter à 30 événements par page
            event_data = [["Heure", "ID", "Direction", "Ligne", "Confiance"]]
            for evt in events[:30]:
                event_data.append([
                    evt.get("datetime", "")[-8:],
                    str(evt.get("track_id", "")),
                    evt.get("direction", ""),
                    evt.get("line", ""),
                    f"{evt.get('confidence', 0):.2f}",
                ])

            event_table = Table(
                event_data,
                colWidths=[3 * cm, 2 * cm, 3 * cm, 4 * cm, 2.5 * cm],
            )
            event_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2e7d32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#9e9e9e")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    HexColor("#e8f5e9"), HexColor("#c8e6c9"),
                ]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(event_table)
            elements.append(Spacer(1, 15))

        # ─── ALERTES ────────────────────────────────────────────
        if alerts:
            elements.append(Paragraph(
                f"🚨 Alertes ({len(alerts)})", subtitle_style,
            ))

            alert_data = [["Heure", "Type", "Personne", "Message"]]
            for alert in alerts[:20]:
                alert_data.append([
                    alert.get("datetime", "")[-8:],
                    alert.get("alert_type", ""),
                    str(alert.get("person_id", "")),
                    alert.get("message", "")[:50],
                ])

            alert_table = Table(
                alert_data,
                colWidths=[3 * cm, 3 * cm, 2 * cm, 6.5 * cm],
            )
            alert_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#c62828")),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#9e9e9e")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    HexColor("#ffebee"), HexColor("#ffcdd2"),
                ]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(alert_table)

        # ─── PIED DE PAGE ───────────────────────────────────────
        elements.append(Spacer(1, 30))
        elements.append(Paragraph(
            f"Rapport généré automatiquement par {self.project_name} v1.0 | "
            f"{self.company_name} | Auteur : BAWANA Théodore",
            ParagraphStyle(
                "FooterStyle",
                parent=styles["Normal"],
                fontSize=8,
                textColor=HexColor("#9e9e9e"),
                alignment=TA_CENTER,
            ),
        ))

        # Construire le PDF
        doc.build(elements)
        logger.info(f"✅ Rapport PDF généré : {save_path}")
        return save_path

    def _generate_charts(
        self,
        report_date: date,
        stats: Dict,
        events: List[Dict],
    ) -> Optional[str]:
        """Génère les graphiques pour le rapport."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib non disponible, graphiques ignorés")
            return None

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle(
            f"Surveillance-IA — {report_date.strftime('%d/%m/%Y')}",
            fontsize=14, fontweight="bold",
        )

        # 1. Histogramme horaire
        ax = axes[0]
        histogram = stats.get("hourly_histogram", {})
        if histogram:
            hours = list(histogram.keys())
            entries = [v.get("entries", 0) for v in histogram.values()]
            exits = [v.get("exits", 0) for v in histogram.values()]

            x = range(len(hours))
            width = 0.35

            ax.bar([i - width / 2 for i in x], entries, width,
                   label="Entrées", color="#4caf50", alpha=0.8)
            ax.bar([i + width / 2 for i in x], exits, width,
                   label="Sorties", color="#f44336", alpha=0.8)
            ax.set_xticks(list(x))
            ax.set_xticklabels(hours, rotation=45, fontsize=8)
            ax.set_ylabel("Nombre de passages")
            ax.set_title("Passages par heure")
            ax.legend()
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, "Pas de données", ha="center", va="center")
            ax.set_title("Passages par heure")

        # 2. Courbe d'occupation cumulée
        ax = axes[1]
        if events:
            # Calculer l'occupation au fil du temps
            sorted_events = sorted(events, key=lambda e: e.get("timestamp", 0))
            times = []
            occupancy = []
            current = 0
            for evt in sorted_events:
                if evt.get("direction") == "entry":
                    current += 1
                elif evt.get("direction") == "exit":
                    current = max(0, current - 1)
                t = evt.get("datetime", "")
                times.append(t[-8:] if len(t) > 8 else t)
                occupancy.append(current)

            if len(times) > 50:
                step = len(times) // 50
                times = times[::step]
                occupancy = occupancy[::step]

            ax.fill_between(range(len(times)), occupancy, alpha=0.3, color="#1565c0")
            ax.plot(range(len(times)), occupancy, color="#1565c0", linewidth=2)
            ax.set_xticks(range(0, len(times), max(1, len(times) // 10)))
            ax.set_xticklabels(
                [times[i] for i in range(0, len(times), max(1, len(times) // 10))],
                rotation=45, fontsize=7,
            )
            ax.set_ylabel("Occupation")
            ax.set_title("Courbe d'occupation")
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, "Pas de données", ha="center", va="center")
            ax.set_title("Courbe d'occupation")

        plt.tight_layout()

        chart_path = os.path.join(
            self.output_dir,
            f"charts_{report_date.isoformat()}.png",
        )
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return chart_path


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Génération de rapports PDF — Surveillance-IA",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date du rapport (YYYY-MM-DD)",
    )
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--demo", action="store_true", help="Générer un rapport démo")

    args = parser.parse_args()

    generator = SurveillanceReportGenerator(output_dir=args.output_dir)

    if args.demo:
        # Données de démonstration
        report_date = date.today()
        stats = {
            "total_entries": 237,
            "total_exits": 215,
            "peak_occupancy": 42,
            "total_unique_persons": 189,
            "avg_presence_time": 420.5,
            "total_alerts": 3,
            "hourly_histogram": {
                "08:00": {"entries": 25, "exits": 5},
                "09:00": {"entries": 45, "exits": 15},
                "10:00": {"entries": 30, "exits": 20},
                "11:00": {"entries": 20, "exits": 25},
                "12:00": {"entries": 35, "exits": 40},
                "13:00": {"entries": 30, "exits": 25},
                "14:00": {"entries": 22, "exits": 30},
                "15:00": {"entries": 15, "exits": 25},
                "16:00": {"entries": 10, "exits": 20},
                "17:00": {"entries": 5, "exits": 10},
            },
        }
        events = [
            {
                "datetime": f"2024-01-15 {h:02d}:{m:02d}:00",
                "track_id": i,
                "direction": "entry" if i % 2 == 0 else "exit",
                "line": "Entrée principale",
                "confidence": 0.92,
                "timestamp": 1705300000 + i * 60,
            }
            for i, (h, m) in enumerate(
                [(8, 15), (8, 22), (9, 5), (9, 30), (10, 0),
                 (10, 45), (11, 15), (12, 0), (13, 30), (14, 0)]
            )
        ]
        alerts = [
            {
                "datetime": "2024-01-15 10:30:00",
                "alert_type": "threshold_exceeded",
                "person_id": 15,
                "message": "Personne ID:15 présente depuis 10 min",
            },
        ]

        path = generator.generate_daily_report(
            report_date, stats, events, alerts,
        )
        print(f"\n📄 Rapport démo généré : {path}")
    else:
        target = date.fromisoformat(args.date)
        # En production, récupérer les données depuis l'API/DB
        print(f"Rapport pour le {target} — connecter à l'API pour les données")


if __name__ == "__main__":
    main()
