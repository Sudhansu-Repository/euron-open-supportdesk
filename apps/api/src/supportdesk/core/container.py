"""Process-wide services, built once in the app lifespan (or the worker) and shared.

Holding them in one object (on ``app.state``) instead of module globals keeps the app
factory re-entrant and lets tests build an isolated container per app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from supportdesk.ai.providers.base import Embedder
from supportdesk.ai.providers.hash_embed import HashEmbedder
from supportdesk.ai.providers.local_embed import LocalEmbedder
from supportdesk.core.aws import aws_client
from supportdesk.core.config import Settings
from supportdesk.core.db import Database
from supportdesk.core.hub import Hub
from supportdesk.core.kv import KV, create_kv
from supportdesk.core.sealing import KeySealer, KmsSealer, LocalSealer
from supportdesk.core.storage import LocalStorage, ObjectStorage, S3Storage


def build_http_client(timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        follow_redirects=False,
        headers={"user-agent": "EuronOpenSupportDesk/0.1"},
    )


@dataclass
class Container:
    settings: Settings
    db: Database
    kv: KV
    # Outbound calls: AI providers, crawled pages, webhooks.
    http: httpx.AsyncClient
    sealer: KeySealer
    storage: ObjectStorage
    hub: Hub
    # The deployment's default embedder (local fastembed, or the test hash embedder).
    local_embedder: Embedder
    # Remote embedders built from organisation settings, by configuration.
    embedders: dict[tuple[Any, ...], Embedder] = field(default_factory=dict)

    @classmethod
    def build(cls, settings: Settings) -> Container:
        sealer: KeySealer = (
            KmsSealer(aws_client(settings, "kms"), settings.kms_key_id)
            if settings.key_mode == "kms"
            else LocalSealer(settings.local_master_key)
        )
        storage: ObjectStorage = (
            S3Storage(aws_client(settings, "s3"), settings.objects_bucket)
            if settings.storage == "s3"
            else LocalStorage(settings.local_storage_dir)
        )
        local: Embedder = (
            HashEmbedder()
            if settings.embedder == "hash"
            else LocalEmbedder(settings.local_embedding_model, settings.model_cache_dir)
        )
        return cls(
            settings=settings,
            db=Database(
                settings.database_url,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
            ),
            kv=create_kv(settings.redis_url, settings.memory_cache_max_bytes),
            http=build_http_client(settings.ai_timeout_s),
            sealer=sealer,
            storage=storage,
            hub=Hub.build(settings.redis_url, settings.database_url),
            local_embedder=local,
        )

    async def close(self) -> None:
        await self.hub.close()
        await self.http.aclose()
        await self.kv.close()
        await self.db.dispose()
