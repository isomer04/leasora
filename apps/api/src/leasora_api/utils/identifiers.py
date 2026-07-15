"""Identifier generation utilities."""

import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def generate_lease_id() -> str:
    """Generate a unique lease ID in the form ``lease_<8-hex-chars>``."""
    return f"lease_{uuid.uuid4().hex[:8]}"
