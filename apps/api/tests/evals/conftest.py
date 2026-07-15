import pytest


@pytest.fixture
def synthetic_lease():
    """Return synthetic lease for testing."""
    return {
        "id": "synthetic-lease-1",
        "content": "This is a synthetic lease for testing purposes.",
        "clauses": [],
    }
