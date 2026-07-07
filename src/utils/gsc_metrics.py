"""
Shared aggregation helpers over ContentPerformanceMetric rows
(source="search_console"). Used by ContentScoringService and
ContentPerformanceDashboardService so both compute sums/averages the same
way (impression-weighted position, not naive average-of-averages).
"""

from typing import Optional, Sequence

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
