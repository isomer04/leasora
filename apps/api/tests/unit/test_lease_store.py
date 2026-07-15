"""Unit tests for LeaseStore.update() (post-ingest metadata patching)."""

from leasora_api.services.ingest.lease_store import LeaseStore


def test_update_patches_only_specified_fields(tmp_path):
    store = LeaseStore(tmp_path / "leases.json")
    store.add(lease_id="lease_1", name="Test Lease", tenant="Jane", landlord="", chunk_count=5)

    updated = store.update("lease_1", {"rent_amount": "$2,000/month", "location": "123 Main St"})

    assert updated is not None
    assert updated.rent_amount == "$2,000/month"
    assert updated.location == "123 Main St"
    # Unspecified fields keep their placeholder / original value.
    assert updated.start_date == "Not yet extracted"
    assert updated.tenant == "Jane"


def test_update_returns_none_for_missing_lease(tmp_path):
    store = LeaseStore(tmp_path / "leases.json")

    result = store.update("does-not-exist", {"rent_amount": "$100"})

    assert result is None


def test_update_persists_across_store_instances(tmp_path):
    path = tmp_path / "leases.json"
    store = LeaseStore(path)
    store.add(lease_id="lease_1", name="Test Lease", tenant="", landlord="", chunk_count=1)
    store.update("lease_1", {"start_date": "2024-01-01"})

    reloaded = LeaseStore(path)
    lease = reloaded.get("lease_1")

    assert lease is not None
    assert lease.start_date == "2024-01-01"


def test_update_ignores_placeholder_echo(tmp_path):
    """Defense-in-depth: if the LLM ever echoes back the 'Not yet
    extracted' placeholder for a field, update() must not overwrite the
    existing value with that garbage. Other fields in the same call still
    apply normally.
    """
    store = LeaseStore(tmp_path / "leases.json")
    store.add(lease_id="lease_1", name="Test Lease", tenant="", landlord="", chunk_count=1)
    store.update("lease_1", {"start_date": "2024-01-01"})

    updated = store.update(
        "lease_1",
        {"start_date": "Not yet extracted", "location": "123 Main St"},
    )

    assert updated is not None
    # start_date keeps the real value; the placeholder echo is dropped.
    assert updated.start_date == "2024-01-01"
    # Sibling fields still apply.
    assert updated.location == "123 Main St"
