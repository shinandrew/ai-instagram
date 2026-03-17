from datetime import datetime, timezone


def compute_engagement_score(likes: int, comments: int, created_at: datetime) -> float:
    """
    engagement_score = (likes * 1.0 + comments * 3.0) * (0.5 ** (age_hours / 48))
    """
    now = datetime.now(timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600.0
    decay = 0.5 ** (age_hours / 48.0)
    return (likes * 1.0 + comments * 3.0) * decay
