import logging
from collections import Counter
from typing import Dict, List

from src.flow.states.rext import Competitor

logger = logging.getLogger(__name__)

VALID_INTENTS = (
    "informational",
    "commercial",
    "navigational",
    "transactional",
)


def _normalize_intent(intent: str) -> str:
    normalized = (intent or "").strip().lower()
    if normalized in VALID_INTENTS:
        return normalized
    return "informational"


def _winner_from_distribution(distribution: Dict[str, int]) -> str | None:
    if not distribution:
        return None

    best_intent = None
    best_score = -1

    # Deterministic tie-breaker by intent name.
    for raw_intent, raw_score in sorted(distribution.items(), key=lambda item: str(item[0]).lower()):
        intent = _normalize_intent(str(raw_intent))
        score = int(raw_score or 0)
        if score > best_score:
            best_intent = intent
            best_score = score

    return best_intent if best_score > 0 else None


def get_serp_intents_from_competitors(
    competitors: List[Competitor],
    fallback_intent: str = "informational",
) -> Dict[str, object]:
    """
    Compute intents from SERP competitors only.

    Rules:
    - main_intent: intent with highest competitor-majority support.
    - foreign_intent: second-highest competitor-majority intent.
    - if no/insufficient signals, fallback to informational.
    """
    fallback = _normalize_intent(fallback_intent)
    winner_counts: Counter[str] = Counter()

    for competitor in competitors or []:
        winner = _winner_from_distribution(competitor.get("intent_distribution", {}))
        if winner:
            winner_counts[winner] += 1

    if not winner_counts:
        return {
            "main_intent": fallback,
            "foreign_intent": fallback,
            "intent_counts": {},
            "total_competitors_classified": 0,
        }

    sorted_counts = sorted(
        winner_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    main_intent = sorted_counts[0][0]
    foreign_intent = sorted_counts[1][0] if len(sorted_counts) > 1 else fallback

    logger.info(
        "SERP intent distribution from competitors: main=%s, foreign=%s, counts=%s",
        main_intent,
        foreign_intent,
        dict(sorted_counts),
    )

    return {
        "main_intent": main_intent,
        "foreign_intent": foreign_intent,
        "intent_counts": dict(sorted_counts),
        "total_competitors_classified": int(sum(winner_counts.values())),
    }
