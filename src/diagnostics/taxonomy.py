"""AST-based gaming taxonomy classifier.

Classifies candidate solutions into gaming strategies per PRODUCT.md
Feature B: ``HARDCODED``, ``SPECIFICATION_SHORTCUT``, and
``JUDGE_MANIPULATION``.
"""

from typing import Literal

GamingTaxonomy = Literal[
    "HARDCODED",
    "SPECIFICATION_SHORTCUT",
    "JUDGE_MANIPULATION",
    "NONE",
]


def classify(candidate_code: str) -> GamingTaxonomy:
    """Classify a candidate solution's gaming strategy via AST analysis.

    Args:
        candidate_code: Untrusted candidate solution source.

    Returns:
        The detected gaming taxonomy label, or ``"NONE"`` if no gaming
        pattern is detected.
    """
    raise NotImplementedError("AST-based gaming classification not yet implemented.")
