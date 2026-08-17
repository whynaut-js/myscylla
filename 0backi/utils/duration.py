import re
from datetime import timedelta

# Matches things like "10m", "1h", "2d", "30s"
_PATTERN = re.compile(r"^(\d+)([smhd])$")

_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


def parse_duration(text: str) -> timedelta | None:
    """Turn '10m', '1h', '2d' etc into a timedelta. Returns None if invalid."""
    match = _PATTERN.match(text.strip().lower())
    if not match:
        return None
    amount, unit = match.groups()
    return timedelta(**{_UNITS[unit]: int(amount)})
