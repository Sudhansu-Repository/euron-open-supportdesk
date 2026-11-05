"""Build an organisation's AI runtime (chat model, embedder) from its settings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from supportdesk.ai.providers.anthropic import AnthropicChat
from supportdesk.ai.providers.base import ChatModel, Embedder
from supportdesk.ai.providers.ollama import OllamaChat, OllamaEmbedder
from supportdesk.ai.providers.openai import OpenAIChat, OpenAIEmbedder
from supportdesk.core.container import Container
from supportdesk.org.schemas import AiConfig


@dataclass(frozen=True)
class AiRuntime:
    config: AiConfig
    # None for the extractive provider: no model, answers are quoted from the knowledge.
    chat: ChatModel | None
    embedder: Embedder

    @property
    def provider(self) -> str:
        return self.config.provider


def chat_model(container: Container, config: AiConfig, api_key: str | None) -> ChatModel | None:
    s = container.settings
    endpoint = config.endpoint(s.ollama_url)
    common = {"timeout_s": s.ai_timeout_s, "allow_private": s.ai_allow_private_endpoints}
    if config.provider == "extractive" or endpoint is None:
        return None
    if config.provider == "ollama":
        return OllamaChat(container.http, endpoint, **common)  # type: ignore[arg-type]
    if config.provider == "anthropic":
        return AnthropicChat(container.http, endpoint, api_key, **common)  # type: ignore[arg-type]
    return OpenAIChat(container.http, endpoint, api_key, **common)  # type: ignore[arg-type]


def embedder(container: Container, config: AiConfig, api_key: str | None) -> Embedder:
    if config.embedder == "local" or not config.embed_model or not config.embed_dims:
        return container.local_embedder
    s = container.settings
    key = (config.embedder, config.embed_base_url, config.embed_model, config.embed_dims, api_key)
    cached = container.embedders.get(key)
    if cached is not None:
        return cached
    common = {"timeout_s": s.ai_timeout_s, "allow_private": s.ai_allow_private_endpoints}
    built: Embedder
    if config.embedder == "ollama":
        built = OllamaEmbedder(
            container.http,
            config.embed_base_url or s.ollama_url,
            config.embed_model,
            config.embed_dims,
            **common,  # type: ignore[arg-type]
        )
    else:
        built = OpenAIEmbedder(
            container.http,
            config.embed_base_url or config.base_url or "https://api.openai.com/v1",
            api_key,
            config.embed_model,
            config.embed_dims,
            **common,  # type: ignore[arg-type]
        )
    container.embedders[key] = built
    return built


async def runtime_for(container: Container, org_id: uuid.UUID) -> AiRuntime:
    from supportdesk.org.service import load_settings, unseal_api_key

    async with container.db.sessionmaker() as session:
        bundle = await load_settings(session, org_id)
    api_key = await unseal_api_key(container, bundle)
    return AiRuntime(
        config=bundle.ai,
        chat=chat_model(container, bundle.ai, api_key),
        embedder=embedder(container, bundle.ai, api_key),
    )
