"""
Query complexity classifier — routes questions to different generation strategies.

Drives how many SQL candidates are generated per query:
  simple  → 1 candidate (single-shot, fast)
  medium  → 1 candidate
  complex → 2 candidates (best-of-N with fallback execution)
"""

import re

# Signals that indicate a multi-dimensional or analytically complex question
_COMPLEX_SIGNALS = [
    r"\bby\s+\w+",                   # "by channel", "by language"
    r"\bversus\b|\bvs\.?\b",          # comparisons
    r"\bcompared?\s+to\b",
    r"\bbreakdown\b",
    r"\bfunnel\b|\bgap\b",
    r"\bfor\s+each\b",
    r"\btop\s+\d+.*\bby\b",           # "top 10 users by output"
    r"\btrend\b",
    r"\bover\s+(time|month|week)",
    r"\bcross\b",
    r"\bper\s+\w+",                   # "per channel", "per user"
    r"\brate\b|\bpercentage\b",
    r"\bmonth.*(over|by)\b",
]


def classify_complexity(question: str) -> str:
    """Returns 'simple', 'medium', or 'complex'."""
    q = question.lower()
    matches = sum(1 for p in _COMPLEX_SIGNALS if re.search(p, q))
    if matches >= 2:
        return "complex"
    elif matches == 1:
        return "medium"
    return "simple"


def n_candidates(complexity: str, explore: bool = False) -> int:
    """
    Number of SQL candidates to generate.
    N=2 only when the query is complex AND the user explicitly requested deep exploration.
    All other cases use N=1 to avoid adding latency.
    """
    return 2 if complexity == "complex" and explore else 1
