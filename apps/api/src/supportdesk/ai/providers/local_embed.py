"""Embeddings computed in the process with fastembed (ONNX Runtime on the CPU).

The default embedder, so a fresh install needs no API key and no GPU. The model (about
130 MB for bge-small-en-v1.5) is downloaded once into ``MODEL_CACHE_DIR``, which the
Compose file keeps in a volume that survives ``make down``. Loading and inference run in a
worker thread so the event loop keeps serving requests.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from supportdesk.ai.providers.base import EmbedKind, ProviderError, normalize

# Output size per supported model; anything else is refused at configuration time.
MODEL_DIMS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "intfloat/multilingual-e5-small": 384,
}

_models: dict[str, Any] = {}
_lock = threading.Lock()


def _load(model: str, cache_dir: str) -> Any:
    with _lock:
        if model not in _models:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - the images install it
                raise ProviderError(
                    "Local embeddings need the local-embeddings extra (fastembed)",
                    retryable=False,
                ) from exc
            _models[model] = TextEmbedding(model_name=model, cache_dir=cache_dir)
        return _models[model]


class LocalEmbedder:
    def __init__(self, model: str, cache_dir: str) -> None:
        if model not in MODEL_DIMS:
            raise ProviderError(f"Unsupported local embedding model {model!r}", retryable=False)
        self.model = model
        self.cache_dir = cache_dir
        self.name = f"local:{model}"
        self.dims = MODEL_DIMS[model]

    def _run(self, texts: list[str], kind: EmbedKind) -> list[list[float]]:
        engine = _load(self.model, self.cache_dir)
        if kind == "query":
            rows = engine.query_embed(texts)
        else:
            rows = engine.passage_embed(texts, batch_size=32)
        return [normalize([float(v) for v in row]) for row in rows]

    async def embed(self, texts: list[str], *, kind: EmbedKind = "document") -> list[list[float]]:
        if not texts:
            return []
        try:
            return await asyncio.to_thread(self._run, texts, kind)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Local embedding failed ({type(exc).__name__})") from exc

    async def warm(self) -> None:
        """Load (and on first run download) the model before the first request needs it."""
        await self.embed(["warm up"], kind="query")
