"""
═══════════════════════════════════════════════════════════════
MODULE 10 (LEGACY) — Compatibilité Ascendante
═══════════════════════════════════════════════════════════════
Ce fichier est un wrapper de compatibilité.
Toute la logique est dans person_manager.py (module universel).

Utilisation recommandée :
    from src.person_manager import PersonManager       # universel
    from src.person_manager import StudentManager      # backward-compat école

Ce fichier est conservé uniquement pour ne pas casser les imports
existants. Il sera supprimé dans une version future.
═══════════════════════════════════════════════════════════════
"""

import warnings

# Re-export depuis le module universel
from src.person_manager import (  # noqa: F401
    PersonManager,
    StudentManager,
    PROFILS,
)

warnings.warn(
    "Le module 'src.student' est obsolète. "
    "Utilisez 'src.person_manager' à la place.\n"
    "  → from src.person_manager import PersonManager   # universel\n"
    "  → from src.person_manager import StudentManager   # backward-compat école",
    DeprecationWarning,
    stacklevel=2,
)
