"""Fetching web pages for the knowledge base, safely.

Every hop (the URL and each redirect) is checked before it is requested: http(s) only, no
instance metadata, and no private or loopback addresses unless the deployment allows them
(checked after DNS resolution, so a public name pointing inside the network is refused).
Bodies are streamed and cut at the upload limit. robots.txt is honoured for our user
agent. Sitemaps are read for same-host pages only, up to the crawl limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from supportdesk.core.net import check_url, host_of, is_private_host, peer_is_safe, resolves_safely

USER_AGENT = "EuronOpenSupportDesk/0.1 (+knowledge import)"
MAX_REDIRECTS = 4
TIMEOUT_S = 20.0
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


class FetchError(Exception):
    """Shown on the source: why the page could not be imported."""


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    body: bytes


async def _safe(url: str, allow_private: bool) -> str:
    try:
        url = check_url(url, "URL")
    except ValueError as exc:
        raise FetchError(str(exc)) from exc
    if not allow_private and is_private_host(host_of(url)):
        raise FetchError("Private and loopback addresses cannot be imported")
    if not await resolves_safely(url, allow_private=allow_private):
        raise FetchError("The address resolves to a private or forbidden network")
    return url


async def fetch(
    client: httpx.AsyncClient, url: str, *, max_bytes: int, allow_private: bool
) -> Fetched:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        current = await _safe(current, allow_private)
        try:
            async with client.stream(
                "GET",
                current,
                headers={"user-agent": USER_AGENT, "accept": "text/html,text/plain,*/*;q=0.5"},
                timeout=TIMEOUT_S,
            ) as resp:
                if not peer_is_safe(resp, allow_private=allow_private):
                    raise FetchError("The address connected to a private or forbidden network")
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    current = urljoin(current, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"The page answered {resp.status_code}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(f"The page is larger than {max_bytes:,} bytes")
                    chunks.append(chunk)
                return Fetched(
                    current, resp.headers.get("content-type", "text/html"), b"".join(chunks)
                )
        except httpx.TimeoutException as exc:
            raise FetchError("The page took too long to answer") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"The page could not be reached ({type(exc).__name__})") from exc
    raise FetchError("Too many redirects")


async def allowed_by_robots(client: httpx.AsyncClient, url: str, allow_private: bool) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        fetched = await fetch(client, robots_url, max_bytes=512_000, allow_private=allow_private)
    except FetchError:
        return True  # no robots.txt (or unreachable): allowed
    parser = RobotFileParser()
    parser.parse(fetched.body.decode("utf-8", "replace").splitlines())
    return parser.can_fetch(USER_AGENT, url)


def sitemap_urls(xml: bytes, base: str, limit: int) -> list[str]:
    host = urlsplit(base).hostname
    out: list[str] = []
    for loc in _LOC.findall(xml.decode("utf-8", "replace")):
        absolute = urljoin(base, loc)
        if urlsplit(absolute).hostname == host and absolute not in out:
            out.append(absolute)
        if len(out) >= limit:
            break
    return out
