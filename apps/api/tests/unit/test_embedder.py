from leasora_api.services.retrieval.embedder import Embedder


class _FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _FakeModel:
    """Stand-in for SentenceTransformer that returns deterministic vectors."""

    def encode(self, texts: list[str], convert_to_numpy: bool = True) -> list[_FakeVector]:
        return [_FakeVector([float(len(text)), 0.0, 1.0]) for text in texts]


def test_embedder_does_not_load_model_on_construction():
    """Constructing an Embedder must never trigger a model download."""
    embedder = Embedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert embedder._model is None


def test_embed_documents_returns_empty_list_for_empty_input():
    embedder = Embedder(model_name="fake-model")
    assert embedder.embed_documents([]) == []


def test_embed_documents_lazy_loads_and_returns_vectors(monkeypatch):
    embedder = Embedder(model_name="fake-model")
    embedder._model = _FakeModel()  # simulate already-loaded model

    vectors = embedder.embed_documents(["hello", "world!"])

    assert vectors == [[5.0, 0.0, 1.0], [6.0, 0.0, 1.0]]


def test_embed_query_returns_single_vector():
    embedder = Embedder(model_name="fake-model")
    embedder._model = _FakeModel()

    vector = embedder.embed_query("hi")

    assert vector == [2.0, 0.0, 1.0]


async def test_aembed_documents_offloads_to_thread():
    embedder = Embedder(model_name="fake-model")
    embedder._model = _FakeModel()

    vectors = await embedder.aembed_documents(["abc"])

    assert vectors == [[3.0, 0.0, 1.0]]


async def test_aembed_query_offloads_to_thread():
    embedder = Embedder(model_name="fake-model")
    embedder._model = _FakeModel()

    vector = await embedder.aembed_query("abcd")

    assert vector == [4.0, 0.0, 1.0]
