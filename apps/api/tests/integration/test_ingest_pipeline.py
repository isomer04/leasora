"""Integration round trip: real PDF -> chunks -> embeddings -> ChromaDB.

Uses the small real sentence-transformers model (already cached locally) so
this test exercises the true pipeline end to end, not mocks. Skips cleanly
if the demo fixture is not present.
"""

from pathlib import Path

import pytest

from leasora_api.services.ingest.pipeline import IngestPipeline
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.vector_store import ChromaStore

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "data" / "test-fixtures"
DEMO_LEASE = FIXTURES_DIR / "demo_lease.pdf"


@pytest.mark.skipif(not DEMO_LEASE.exists(), reason="demo_lease.pdf fixture not present")
async def test_ingest_and_query_round_trip(tmp_path):
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"), collection_name="ingest-test")
    embedder = Embedder()  # real model, already cached locally

    pipeline = IngestPipeline(embedder_=embedder, vector_store=store)

    result = await pipeline.ingest(str(DEMO_LEASE), lease_id="lease-demo")

    assert result["lease_id"] == "lease-demo"
    assert result["chunk_count"] > 0

    query_vector = await embedder.aembed_query("What is the rent?")
    results = await store.query(
        embedding=query_vector, top_k=3, where={"lease_id": {"$eq": "lease-demo"}}
    )

    assert results
    for result_row in results:
        assert result_row["metadata"]["lease_id"] == "lease-demo"
        assert result_row["metadata"]["source"] == "demo_lease.pdf"
        assert isinstance(result_row["metadata"]["page"], int)
