"""Timezone helpers for user-facing API timestamps."""

from datetime import datetime
from zoneinfo import ZoneInfo


NEPAL_TIMEZONE = ZoneInfo("Asia/Kathmandu")


def serialize_nepal_datetime(value):
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=NEPAL_TIMEZONE)
    return value.astimezone(NEPAL_TIMEZONE).strftime(
        "%b %-d, %Y, %-I:%M %p NPT"
    )