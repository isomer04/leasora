# Golden evaluation dataset

`questions.jsonl` contains labeled question/answer pairs used by the
retrieval + answer-quality evaluation harness (`services/eval/runner.py`,
`cli/eval.py`).

## Provenance

Ground-truth `relevant_clause_ids` are pinned to the chunk IDs produced by
ingesting `data/test-fixtures/demo_lease.pdf` with `lease_id="golden-demo-lease"`
through `IngestPipeline`. The demo lease is a synthetic,
non-identifying fixture (fake names, fake address, fake account numbers)
created for testing — see the "THIS DOCUMENT IS FOR TESTING PURPOSES" banner
on page 1 of the PDF itself.

The eval runner ingests this fixture into an isolated, temporary ChromaDB
directory before running (see `services/eval/runner.py`), so golden clause
IDs must stay in sync with the current chunking behavior. If chunking logic
in `services/ingest/chunker.py` changes in a way that reflows clause
boundaries, re-run the dump below and update `relevant_clause_ids`
accordingly:

```python
import asyncio
from leasora_api.services.ingest.pipeline import IngestPipeline
from leasora_api.services.retrieval.embedder import Embedder
from leasora_api.services.retrieval.vector_store import ChromaStore

async def main():
    store = ChromaStore(persist_dir="/tmp/golden-chroma", collection_name="golden-demo-lease")
    pipeline = IngestPipeline(embedder_=Embedder(), vector_store=store)
    print(await pipeline.ingest("data/test-fixtures/demo_lease.pdf", lease_id="golden-demo-lease"))

asyncio.run(main())
```

## Categories

- `factual`: direct lookups answerable from a single clause (rent amount,
  due date, deposit amount, notice periods, etc).
- `statute`: questions that hinge on a California Civil Code citation present
  in the lease text.
- `red_flag`: questions about clauses the demo lease explicitly flags as
  "RED FLAG" or "UNUSUAL" compared to standard California lease practice.
- `out_of_scope`: questions with no answer anywhere in the lease. The system
  is expected to refuse (`should_refuse: true`) rather than hallucinate.

## Size note

23 questions is intentionally small. Retrieval and answer-quality metric
deltas at this size have wide
confidence intervals — treat single-digit percentage swings between
configurations as noise, not signal, unless they hold up category-by-category.
