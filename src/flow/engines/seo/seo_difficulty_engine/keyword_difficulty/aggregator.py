import statistics

def median(scores: list[float]) -> float:
    return statistics.median(scores) if scores else 0.0
