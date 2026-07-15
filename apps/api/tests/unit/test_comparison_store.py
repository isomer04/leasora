"""Unit tests for the comparison history store (JSON-file-backed)."""

from leasora_api.services.compare.comparison_store import ComparisonStore


def test_add_records_a_comparison(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")

    record = store.add(lease_ids=["lease_a", "lease_b"])

    assert record["lease_ids"] == ["lease_a", "lease_b"]
    assert record["id"].startswith("cmp_")
    assert record["created_at"]


def test_count_reflects_number_of_recorded_comparisons(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")
    assert store.count() == 0

    store.add(lease_ids=["a", "b"])
    store.add(lease_ids=["c", "d"])

    assert store.count() == 2


def test_list_page_returns_most_recent_first(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")
    store.add(lease_ids=["a", "b"])
    store.add(lease_ids=["c", "d"])
    store.add(lease_ids=["e", "f"])

    items, total = store.list_page(page=1, page_size=20)

    assert total == 3
    assert [item["lease_ids"] for item in items] == [["e", "f"], ["c", "d"], ["a", "b"]]


def test_list_page_paginates(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")
    for i in range(5):
        store.add(lease_ids=[f"lease_{i}", f"lease_{i}b"])

    page1, total = store.list_page(page=1, page_size=2)
    page2, _ = store.list_page(page=2, page_size=2)
    page3, _ = store.list_page(page=3, page_size=2)

    assert total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    # Page 1 should have the two most recent (lease_4, lease_3)
    assert page1[0]["lease_ids"] == ["lease_4", "lease_4b"]


def test_list_page_caps_page_size_at_max(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")
    for i in range(3):
        store.add(lease_ids=[f"lease_{i}", f"lease_{i}b"])

    items, _total = store.list_page(page=1, page_size=10_000)

    # Should not error, should just return what's available (capped
    # internally at _MAX_PAGE_SIZE, which is >= 3 here).
    assert len(items) == 3


def test_retention_caps_stored_records(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json", max_records=3)

    for i in range(5):
        store.add(lease_ids=[f"lease_{i}", f"lease_{i}b"])

    assert store.count() == 3
    items, _ = store.list_page(page=1, page_size=10)
    # Only the 3 most recent should remain: lease_4, lease_3, lease_2
    assert [item["lease_ids"][0] for item in items] == ["lease_4", "lease_3", "lease_2"]


def test_empty_store_returns_empty_page(tmp_path):
    store = ComparisonStore(tmp_path / "comparisons.json")

    items, total = store.list_page(page=1, page_size=20)

    assert items == []
    assert total == 0


def test_corrupt_json_file_degrades_to_empty_store(tmp_path, caplog):
    """A corrupt comparisons.json must not crash reads/writes — the store
    treats it as empty (logged at exception level) and subsequent writes
    overwrite it cleanly.
    """
    import logging

    path = tmp_path / "comparisons.json"
    path.write_text("not valid json{", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="leasora_api.services.compare.comparison_store"):
        store = ComparisonStore(path)

        # Reads treat the file as empty.
        assert store.count() == 0
        items, total = store.list_page(page=1, page_size=10)
        assert items == []
        assert total == 0
        # Writes still work and recover the file.
        store.add(lease_ids=["a", "b"])

    assert store.count() == 1
    assert any("Failed to read comparison store" in rec.message for rec in caplog.records)
