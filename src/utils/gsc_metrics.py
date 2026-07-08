"""
Shared aggregation helpers over ContentPerformanceMetric rows
(source="search_console"). Used by ContentScoringService,
ContentPerformanceDashboardService, and OpportunityScoreService so all three
compute sums/averages/expected-CTR the same way (impression-weighted
position, not naive average-of-averages; one shared expected-CTR curve).
"""

from typing import List, Optional, Sequence, Tuple

from src.api.models.content_models.content_performance_metric import ContentPerformanceMetric


def sum_metric(rows: Sequence[ContentPerformanceMetric], key: str) -> float:
    return sum(float((row.metrics or {}).get(key) or 0) for row in rows)


def weighted_avg_position(rows: Sequence[ContentPerformanceMetric]) -> Optional[float]:
    """Impression-weighted average position across a set of daily rows."""
    total_impressions = sum_metric(rows, "impressions")
    if total_impressions <= 0:
        return None
    weighted = sum(
        float((row.metrics or {}).get("position") or 0) * float((row.metrics or {}).get("impressions") or 0)
        for row in rows
    )
    return weighted / total_impressions


# Industry-average expected CTR by average SERP position (an approximation —
# tune to your vertical if you have better benchmark data; Google does not
# publish an official curve). (position, expected_ctr) pairs, interpolated
# piecewise-linearly between points.
EXPECTED_CTR_BY_POSITION: List[Tuple[float, float]] = [
    (1, 0.28), (2, 0.15), (3, 0.11), (4, 0.08), (5, 0.06),
    (6, 0.05), (7, 0.04), (8, 0.03), (9, 0.03), (10, 0.02),
    (15, 0.015), (20, 0.01), (30, 0.005), (50, 0.002),
]


def expected_ctr(position: float) -> float:
    """Piecewise-linear interpolation over the expected-CTR-by-position curve."""
    curve = EXPECTED_CTR_BY_POSITION
    if position <= curve[0][0]:
        return curve[0][1]
    for (pos_a, ctr_a), (pos_b, ctr_b) in zip(curve, curve[1:]):
        if pos_a <= position <= pos_b:
            if pos_b == pos_a:
                return ctr_a
            ratio = (position - pos_a) / (pos_b - pos_a)
            return ctr_a + ratio * (ctr_b - ctr_a)
    return curve[-1][1]
