"""Ollama's native API: the zero-API-key mode with a local model."""

from __future__ import annotations

from typing import Any

import httpx

from supportdesk.ai.providers.base import (
    ChatMessage,
    Completion,
    EmbedKind,
    ProviderError,
    normalize,
)
from supportdesk.ai.providers.http import post_json


class OllamaChat:
    provider = "ollama"

    def __init__(
        self, client: httpx.AsyncClient, base_url: str, *, timeout_s: float, allow_private: bool
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.allow_private = allow_private

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        data = await post_json(
            self.client,
            f"{self.base_url}/api/chat",
            body,
            timeout_s=self.timeout_s,
            allow_private=self.allow_private,
        )
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError("Ollama sent no completion") from exc
        return Completion(
            text=str(text),
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
            model=str(data.get("model") or model),
        )


class OllamaEmbedder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        dims: int,
        *,
        timeout_s: float,
        allow_private: bool,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self.dims = dims
        self.timeout_s = timeout_s
        self.allow_private = allow_private

    async def embed(self, texts: list[str], *, kind: EmbedKind = "document") -> list[list[float]]:
        data = await post_json(
            self.client,
            f"{self.base_url}/api/embed",
            {"model": self.model, "input": texts},
            timeout_s=self.timeout_s,
            allow_private=self.allow_private,
        )
        try:
            vectors = [normalize([float(v) for v in row]) for row in data["embeddings"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Ollama sent an unexpected embedding response") from exc
        if len(vectors) != len(texts) or any(len(v) != self.dims for v in vectors):
            raise ProviderError(
                f"The embedding model returned vectors of the wrong size (expected {self.dims})",
                retryable=False,
            )
        return vectors
