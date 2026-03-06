from typing import List, Optional


# ------------------------------
# Helper scoring functions
# ------------------------------
def bool_score(value: Optional[bool]) -> int:
    return 1 if value else 0


def heading_complexity_score(value: Optional[str]) -> int:
    mapping = {"simple": 1, "moderate": 2, "complex": 3}
    return mapping.get(value, 0)


def normalize(value: float, max_value: float) -> float:
    """Return value in 0-1 range, capped at 1."""
    return min(value / max_value, 1.0)