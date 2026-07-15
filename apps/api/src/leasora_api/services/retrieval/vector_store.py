"""Vector storage service for semantic search via ChromaDB."""

import asyncio
from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

if TYPE_CHECKING:
    import chromadb


class ChunkMetadata(TypedDict, total=False):
    """Metadata stored alongside a chunk embedding."""

    source: str
    page: int
    clause_type: str
    lease_id: str


class RetrievalResult(TypedDict):
    """A single ranked result returned from a vector store query."""

    id: str
    text: str
    metadata: ChunkMetadata
    distance: float


class VectorStore(Protocol):
    """Abstract protocol for vector storage backends."""

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[ChunkMetadata] | None = None,
    ) -> None:
        """Store embeddings and documents.

        Args:
            ids: Unique identifiers for documents
            embeddings: Vector embeddings from model
            documents: Original document texts
            metadatas: Optional per-document metadata (source, page, clause_type)
        """
        ...

    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Find most similar documents.

        Args:
            embedding: Query vector embedding
            top_k: Number of results to return
            where: Optional metadata filter (e.g. {"lease_id": "..."})

        Returns:
            List of matching documents with scores, ranked by distance ascending.
        """
        ...

    async def get_by_lease(self, lease_id: str) -> list[RetrievalResult]:
        """Return all chunks stored for a given lease, unranked.

        Used to build an in-memory BM25 index over a lease's full corpus for
        hybrid (lexical + dense) retrieval. ``distance`` is not meaningful
        here and is set to ``0.0`` for every result.

        Args:
            lease_id: The lease to fetch chunks for.

        Returns:
            All stored chunks for the lease, in no particular order.
        """
        ...

    async def delete_by_lease(self, lease_id: str) -> None:
        """Delete all chunks stored for a given lease.

        Called before re-adding a lease's chunks on re-ingest, so stored IDs
        (``f"{lease_id}::{i}"``) don't collide with a previous ingest of the
        same lease_id.

        Args:
            lease_id: The lease to delete chunks for.
        """
        ...


class ChromaStore:
    """Concrete Chroma vector store implementation."""

    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "leases") -> None:
        """Initialize Chroma store with a lazily-created persistent client.

        Args:
            persist_dir: Directory for persistent storage.
            collection_name: Name of the ChromaDB collection to use.
        """
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: "chromadb.Collection | None" = None
        # ``_ensure_collection`` can be reached from multiple worker threads.
        # Use a lock to ensure concurrent ingests don't create separate
        # ``PersistentClient`` instances pointing at the same directory.
        self._init_lock = Lock()

    def _ensure_collection(self) -> "chromadb.Collection":
        """Lazily construct the persistent client + collection on first use."""
        if self._collection is not None:
            return self._collection
        with self._init_lock:
            if self._collection is None:
                import chromadb

                self._client = chromadb.PersistentClient(path=self.persist_dir)
                self._collection = self._client.get_or_create_collection(
                    self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
        return self._collection

    def _add_sync(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[ChunkMetadata] | None,
    ) -> None:
        collection = self._ensure_collection()
        kwargs: dict[str, Any] = {
            "ids": ids,
            "embeddings": embeddings,
            "documents": documents,
        }
        if metadatas is not None:
            kwargs["metadatas"] = [dict(meta) for meta in metadatas]
        collection.add(**kwargs)

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[ChunkMetadata] | None = None,
    ) -> None:
        """Store embeddings and documents (offloaded to a worker thread)."""
        await asyncio.to_thread(self._add_sync, ids, embeddings, documents, metadatas)

    def _query_sync(
        self,
        embedding: list[float],
        top_k: int,
        where: dict[str, Any] | None,
    ) -> list[RetrievalResult]:
        collection = self._ensure_collection()
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k,
        }
        if where:
            kwargs["where"] = where
        res = collection.query(**kwargs)

        documents = res.get("documents") or []
        if not documents or not documents[0]:
            return []

        ids = (res.get("ids") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0] or [{} for _ in documents[0]]
        distances = (res.get("distances") or [[]])[0]

        results: list[RetrievalResult] = []
        for chunk_id, doc, meta, distance in zip(
            ids, documents[0], metadatas, distances, strict=True
        ):
            results.append(
                RetrievalResult(
                    id=chunk_id,
                    text=doc,
                    metadata=cast(ChunkMetadata, dict(meta or {})),
                    distance=distance,
                )
            )
        return results

    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Find most similar documents (offloaded to a worker thread)."""
        return await asyncio.to_thread(self._query_sync, embedding, top_k, where)

    def _get_by_lease_sync(self, lease_id: str) -> list[RetrievalResult]:
        collection = self._ensure_collection()
        res = collection.get(
            where=cast(Any, {"lease_id": {"$eq": lease_id}}),
            include=["documents", "metadatas"],
        )
        ids = res.get("ids") or []
        documents = res.get("documents") or []
        metadatas = res.get("metadatas") or [{} for _ in documents]

        return [
            RetrievalResult(
                id=chunk_id,
                text=doc,
                metadata=cast(ChunkMetadata, dict(meta or {})),
                distance=0.0,
            )
            for chunk_id, doc, meta in zip(ids, documents, metadatas, strict=True)
        ]

    async def get_by_lease(self, lease_id: str) -> list[RetrievalResult]:
        """Return all chunks stored for a lease (offloaded to a worker thread)."""
        return await asyncio.to_thread(self._get_by_lease_sync, lease_id)

    def _delete_by_lease_sync(self, lease_id: str) -> None:
        collection = self._ensure_collection()
        collection.delete(where=cast(Any, {"lease_id": {"$eq": lease_id}}))

    async def delete_by_lease(self, lease_id: str) -> None:
        """Delete all chunks for a lease (offloaded to a worker thread).

        No-op (does not raise) if the lease has no stored chunks yet, since
        Chroma's ``delete(where=...)`` matching zero rows is a normal case
        for a first-time ingest.
        """
        await asyncio.to_thread(self._delete_by_lease_sync, lease_id)


# Singleton instance for dependency injection. Construction is cheap because
# the ChromaDB client/collection is lazily created on first add/query call.
chroma = ChromaStore()
