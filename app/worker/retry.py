from datetime import datetime, timedelta, timezone


def calculate_next_attempt(attempts: int) -> datetime:
    seconds = min(2**attempts, 300)
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
