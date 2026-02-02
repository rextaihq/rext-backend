from datetime import datetime

def normalize_freshness(date_str):
    if not date_str:
        return 0.3

    try:
        dt = datetime.fromisoformat(date_str)
        days = (datetime.now() - dt).days

        if days <= 30:
            return 1.0
        elif days <= 180:
            return 0.85
        elif days <= 365:
            return 0.4
        else:
            return 0.1
    except Exception:
        return 0.3
