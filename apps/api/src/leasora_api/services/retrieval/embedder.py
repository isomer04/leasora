"""Embedding service for vector generation.

Lazy-loads a sentence-transformers model so importing this module never
triggers a model download or slows down app startup / unit test collection.
The model is only pulled into memory the first time an embedding is actually
requested.
"""

import asyncio
from typing import TYPE_CHECKING

from leasora_api.core.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class Embedder:
    """Generate vector embeddings for documents and queries.

    Uses sentence-transformers to generate dense embeddings for:
    - Document chunks (for storage in the vector store)
    - User queries (for semantic search)

    The underlying model is lazy-loaded on first use so that importing this
    module (or constructing an ``Embedder``) is always cheap and side-effect
    free, which keeps unit tests fast and independent of network access.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize embedder with specified model.

        Args:
            model_name: HuggingFace/sentence-transformers model identifier.
                Defaults to ``settings.embedding_model`` when not provided.
        """
        self.model_name = model_name or get_settings().embedding_model
        self._model: SentenceTransformer | None = None

    def _ensure_loaded(self) -> "SentenceTransformer":
        """Lazily construct the SentenceTransformer model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of document chunks.

        Args:
            texts: List of document chunk texts.

        Returns:
            List of embedding vectors, one per input text (same order).
        """
        if not texts:
            return []
        model = self._ensure_loaded()
        vectors = model.encode(texts, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a single query string.

        Args:
            text: The query text.

        Returns:
            Embedding vector for the query.
        """
        model = self._ensure_loaded()
        vector = model.encode([text], convert_to_numpy=True)[0]
        result: list[float] = vector.tolist()
        return result

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper around :meth:`embed_documents`.

        ``sentence-transformers`` encoding is CPU-bound and synchronous, so
        the blocking call is offloaded to a worker thread to avoid stalling
        the event loop.
        """
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Async wrapper around :meth:`embed_query`.

        See :meth:`aembed_documents` for why this is offloaded to a thread.
        """
        return await asyncio.to_thread(self.embed_query, text)


# Singleton instance for dependency injection. Construction is cheap because
# the model itself is lazy-loaded on first embed call, not here.
embedder = Embedder()
