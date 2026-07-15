"""Timestamp utilities."""

from datetime import datetime, timezone


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()
