"""Anthropic's Messages API."""

from __future__ import annotations

from typing import Any

import httpx

from supportdesk.ai.providers.base import ChatMessage, Completion, ProviderError
from supportdesk.ai.providers.http import post_json

API_VERSION = "2023-06-01"


class AnthropicChat:
    provider = "anthropic"

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

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        max_tokens: int,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> Completion:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        if json_mode:
            system += "\n\nRespond with one JSON object and nothing else."
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages if m.role != "system"
            ],
        }
        if system:
            body["system"] = system
        data = await post_json(
            self.client,
            f"{self.base_url}/v1/messages",
            body,
            headers={"x-api-key": self.api_key or "", "anthropic-version": API_VERSION},
            timeout_s=self.timeout_s,
            allow_private=self.allow_private,
        )
        try:
            text = "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("The AI provider sent no completion") from exc
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            model=str(data.get("model") or model),
        )
