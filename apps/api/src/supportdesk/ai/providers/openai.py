"""Any endpoint speaking the OpenAI wire format: OpenAI, vLLM, Ollama's /v1, a LiteLLM
proxy, Euron Open TokenShield, Groq, Together and so on."""

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


class OpenAIChat:
    provider = "openai"

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None,
        *,
        timeout_s: float,
        allow_private: bool,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.allow_private = allow_private

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}

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
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = await post_json(
            self.client,
            f"{self.base_url}/chat/completions",
            body,
            headers=self._headers(),
            timeout_s=self.timeout_s,
            allow_private=self.allow_private,
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("The AI provider sent no completion") from exc
        usage = data.get("usage") or {}
        return Completion(
            text=str(text),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=str(data.get("model") or model),
        )


class OpenAIEmbedder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None,
        model: str,
        dims: int,
        *,
        timeout_s: float,
        allow_private: bool,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = f"openai:{model}"
        self.dims = dims
        self.timeout_s = timeout_s
        self.allow_private = allow_private

    async def embed(self, texts: list[str], *, kind: EmbedKind = "document") -> list[list[float]]:
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = await post_json(
            self.client,
            f"{self.base_url}/embeddings",
            {"model": self.model, "input": texts},
            headers=headers,
            timeout_s=self.timeout_s,
            allow_private=self.allow_private,
        )
        try:
            rows = sorted(data["data"], key=lambda r: r["index"])
            vectors = [normalize([float(v) for v in r["embedding"]]) for r in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("The embedding provider sent an unexpected response") from exc
        if len(vectors) != len(texts) or any(len(v) != self.dims for v in vectors):
            raise ProviderError(
                f"The embedding model returned vectors of the wrong size (expected {self.dims})",
                retryable=False,
            )
        return vectors
