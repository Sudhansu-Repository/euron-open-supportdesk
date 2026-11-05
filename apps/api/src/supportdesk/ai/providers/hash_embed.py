"""A deterministic embedder for unit tests: hashed word unigrams and bigrams.

It captures word overlap, not meaning, so it is refused in production (see the config
guard). Tests use it to exercise retrieval, caches and clustering without downloading a
model.
"""

from __future__ import annotations

import hashlib
import re
from itertools import pairwise

from supportdesk.ai.providers.base import EmbedKind, normalize
from supportdesk.ai.text import content_words

DIMS = 384


def _bucket(token: str) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
    index = int.from_bytes(digest[:4], "big") % DIMS
    sign = 1.0 if digest[4] & 1 else -1.0
    return index, sign


class HashEmbedder:
    name = "hash:v1"
    dims = DIMS

    def vector(self, text: str) -> list[float]:
        words = content_words(text)
        vec = [0.0] * DIMS
        for token in words + [f"{a}_{b}" for a, b in pairwise(words)]:
            index, sign = _bucket(token)
            vec[index] += sign
        if not any(vec):
            index, sign = _bucket(re.sub(r"\s+", " ", text.lower()).strip() or "empty")
            vec[index] = sign
        return normalize(vec)

    async def embed(self, texts: list[str], *, kind: EmbedKind = "document") -> list[list[float]]:
        return [self.vector(t) for t in texts]
