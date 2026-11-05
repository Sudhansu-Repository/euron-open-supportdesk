"""Shared HTTP handling for remote providers: bounded time, no redirects, safe targets,
and errors classified as retryable or not."""

from __future__ import annotations

from typing import Any

import httpx

from supportdesk.ai.providers.base import ProviderError
from supportdesk.core.net import check_url, peer_is_safe, resolves_safely


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float,
    allow_private: bool,
) -> dict[str, Any]:
    try:
        check_url(url, "AI endpoint")
    except ValueError as exc:
        raise ProviderError(str(exc), retryable=False) from exc
    if not await resolves_safely(url, allow_private=allow_private):
        raise ProviderError("The AI endpoint resolves to a forbidden address", retryable=False)
    try:
        resp = await client.post(url, json=body, headers=headers or {}, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        raise ProviderError("The AI provider timed out", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach the AI provider ({type(exc).__name__})", retryable=True
        ) from exc
    if not peer_is_safe(resp, allow_private=allow_private):
        raise ProviderError("The AI endpoint connected to a forbidden address", retryable=False)
    if resp.status_code >= 400:
        retryable = resp.status_code == 429 or resp.status_code >= 500
        detail = resp.text[:300].replace("\n", " ")
        raise ProviderError(
            f"The AI provider answered {resp.status_code}: {detail}",
            retryable=retryable,
            status=resp.status_code,
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError("The AI provider sent a response that is not JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("The AI provider sent an unexpected response")
    return data
