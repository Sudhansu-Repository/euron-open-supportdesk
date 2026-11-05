"""What every model backend implements.

Adding a provider means adding one file with a class that satisfies ``ChatModel`` or
``Embedder`` and one line in ``registry.py``; nothing else in the AI layer changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class ProviderError(Exception):
    """The provider failed (HTTP error, bad response, timeout). ``retryable`` marks
    failures worth another attempt (timeouts, 429, 5xx)."""

    def __init__(self, message: str, *, retryable: bool = True, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class ChatModel(Protocol):
    provider: str

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> Completion: ...


EmbedKind = Literal["query", "document"]


class Embedder(Protocol):
    name: str
    dims: int

    async def embed(self, texts: list[str], *, kind: EmbedKind = "document") -> list[list[float]]:
        """Unit-length vectors. Some models embed questions and passages differently."""
        ...


def estimate_tokens(text: str) -> int:
    """A conservative token estimate (about four characters per token for English, more
    tokens for other scripts) used to reserve budget before a call; the ledger then
    records what the provider actually reports."""
    if not text:
        return 0
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return math.ceil((len(text) - non_ascii) / 3.5 + non_ascii * 1.2)


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
