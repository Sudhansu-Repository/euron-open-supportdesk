"""Knowledge sources and articles, and the ``kb.ingest`` job that indexes them.

Indexing a source parses, chunks and embeds it outside any transaction, then swaps the
chunks in one transaction: the old version's chunks are deleted and the new ones inserted
together, so retrieval never sees a half-indexed source. Every swap bumps the
organisation's knowledge version, which retires cached answers built on the old text.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportdesk.ai.providers.base import ProviderError
from supportdesk.ai.registry import runtime_for
from supportdesk.audit.service import Actor, audit
from supportdesk.core import jobs
from supportdesk.core.container import Container
from supportdesk.core.db import OrgScope
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.knowledge import fetch as fetching
from supportdesk.knowledge.chunking import ChunkDraft, chunk_document, embedding_text
from supportdesk.knowledge.models import Article, Chunk, Source
from supportdesk.knowledge.parsing import (
    Document,
    ParseError,
    Section,
    detect_kind,
    parse,
    parse_html,
)
from supportdesk.org.models import Org
from supportdesk.org.service import bump_kb_version

INGEST = "kb.ingest"
INDEX_ARTICLE = "kb.article"
EMBED_BATCH = 64


def _now() -> datetime:
    return datetime.now(UTC)


async def add_file(
    container: Container,
    session: AsyncSession,
    actor: Actor,
    filename: str,
    content_type: str | None,
    data: bytes,
    title: str | None = None,
) -> Source:
    if not data:
        raise AppError("The file is empty", code="empty_file")
    if len(data) > container.settings.max_upload_bytes:
        raise AppError(
            f"The file is larger than {container.settings.max_upload_bytes:,} bytes",
            code="file_too_large",
        )
    try:
        detect_kind(filename, content_type)
    except ParseError as exc:
        raise AppError(str(exc), code="unsupported_file") from exc
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)[-200:] or "upload"
    digest = hashlib.sha256(data).hexdigest()
    source = Source(
        org_id=actor.org_id,
        kind="file",
        title=(title or safe_name.rsplit(".", 1)[0])[:300],
        filename=safe_name,
        content_type=content_type,
        sha256=digest,
        size=len(data),
        created_by=actor.id,
    )
    session.add(source)
    await session.flush()
    source.storage_key = f"orgs/{actor.org_id}/kb/{source.id}/{digest}"
    await container.storage.put(
        source.storage_key, data, content_type or "application/octet-stream"
    )
    await jobs.enqueue(
        session, INGEST, {"source_id": str(source.id)}, org_id=actor.org_id, max_attempts=3
    )
    audit(session, actor, "kb.source_added", "source", source.id, kind="file", size=len(data))
    await session.commit()
    return source


async def add_url(
    container: Container,
    session: AsyncSession,
    actor: Actor,
    url: str,
    sitemap: bool,
    title: str | None,
) -> Source:
    from supportdesk.core.net import check_url

    try:
        url = check_url(url, "URL")
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_url") from exc
    source = Source(
        org_id=actor.org_id,
        kind="sitemap" if sitemap else "url",
        title=(title or url)[:300],
        url=url,
        created_by=actor.id,
    )
    session.add(source)
    await session.flush()
    await jobs.enqueue(
        session, INGEST, {"source_id": str(source.id)}, org_id=actor.org_id, max_attempts=3
    )
    audit(session, actor, "kb.source_added", "source", source.id, kind=source.kind)
    await session.commit()
    return source


async def get_source(session: AsyncSession, scope: OrgScope, source_id: uuid.UUID) -> Source:
    source = await session.get(Source, source_id)
    if source is None or source.org_id != scope.org_id:
        raise NotFoundError("Knowledge source not found")
    return source


async def reindex(session: AsyncSession, actor: Actor, source_id: uuid.UUID) -> Source:
    source = await get_source(session, actor.scope, source_id)
    source.status = "queued"
    source.error = None
    await jobs.enqueue(
        session, INGEST, {"source_id": str(source.id)}, org_id=actor.org_id, max_attempts=3
    )
    audit(session, actor, "kb.source_reindexed", "source", source.id)
    await session.commit()
    return source


async def schedule_reindex_all(session: AsyncSession, org_id: uuid.UUID) -> None:
    """After the embedder changes every chunk must be embedded again."""
    sources = (await session.scalars(select(Source.id).where(Source.org_id == org_id))).all()
    for source_id in sources:
        await jobs.enqueue(
            session, INGEST, {"source_id": str(source_id)}, org_id=org_id, max_attempts=3
        )
    articles = (
        await session.scalars(
            select(Article.id).where(Article.org_id == org_id, Article.status == "published")
        )
    ).all()
    for article_id in articles:
        await jobs.enqueue(session, INDEX_ARTICLE, {"article_id": str(article_id)}, org_id=org_id)
    await session.execute(update(Source).where(Source.org_id == org_id).values(status="queued"))


async def delete_source(
    container: Container, session: AsyncSession, actor: Actor, source_id: uuid.UUID
) -> None:
    source = await get_source(session, actor.scope, source_id)
    key = source.storage_key
    await session.delete(source)  # chunks cascade
    await bump_kb_version(session, actor.org_id)
    audit(session, actor, "kb.source_deleted", "source", source_id)
    await session.commit()
    if key:
        # An orphaned object is harmless: the row (and so every reference) is gone.
        with contextlib.suppress(Exception):
            await container.storage.delete(key)


async def _documents(container: Container, source: Source) -> list[Document]:
    s = container.settings
    if source.kind == "file":
        assert source.storage_key
        assert source.filename
        data = await container.storage.get(source.storage_key)
        doc = await asyncio.to_thread(
            parse, data, source.filename, source.content_type, source.title
        )
        return [doc]
    assert source.url
    if source.kind == "url":
        pages = [source.url]
    else:
        fetched = await fetching.fetch(
            container.http,
            source.url,
            max_bytes=s.max_upload_bytes,
            allow_private=s.allow_private_urls,
        )
        pages = fetching.sitemap_urls(fetched.body, fetched.url, s.max_crawl_pages)
        if not pages:
            raise fetching.FetchError("The sitemap lists no pages on this site")
    docs: list[Document] = []
    errors: list[str] = []
    # One import may not hold more than this much fetched content in memory at once.
    budget = s.max_upload_bytes * 4
    for page in pages:
        if budget <= 0:
            errors.append("stopped: the sitemap's pages exceed the import size budget")
            break
        if not await fetching.allowed_by_robots(container.http, page, s.allow_private_urls):
            errors.append(f"{page}: disallowed by robots.txt")
            continue
        try:
            fetched = await fetching.fetch(
                container.http,
                page,
                max_bytes=s.max_upload_bytes,
                allow_private=s.allow_private_urls,
            )
            budget -= len(fetched.body)
            text = fetched.body.decode("utf-8", "replace")
            if "html" in fetched.content_type or text.lstrip()[:1] == "<":
                doc = await asyncio.to_thread(parse_html, text, source.title, fetched.url)
            else:
                doc = Document(
                    title=source.title, sections=[Section(None, text, anchor=fetched.url)]
                )
            docs.append(doc)
        except (fetching.FetchError, ParseError) as exc:
            errors.append(f"{page}: {exc}")
    if not docs:
        raise fetching.FetchError("; ".join(errors[:3]) or "Nothing could be imported")
    return docs


async def _embed(
    container: Container, org_id: uuid.UUID, drafts: list[ChunkDraft]
) -> tuple[list[list[float]], str]:
    runtime = await runtime_for(container, org_id)
    vectors: list[list[float]] = []
    for i in range(0, len(drafts), EMBED_BATCH):
        batch = drafts[i : i + EMBED_BATCH]
        vectors.extend(
            await runtime.embedder.embed(
                [embedding_text(d.title, d.heading, d.text) for d in batch], kind="document"
            )
        )
    return vectors, runtime.embedder.name


@jobs.handles(INGEST)
async def ingest(ctx: jobs.JobContext) -> None:
    container = ctx.container
    source_id = uuid.UUID(ctx.payload["source_id"])
    async with container.db.sessionmaker() as session:
        source = await session.get(Source, source_id)
        if source is None:
            return
        source.status = "processing"
        source.error = None
        await session.commit()
    try:
        docs = await _documents(container, source)
        drafts: list[ChunkDraft] = []
        url_base = source.url
        for doc in docs:
            for d in chunk_document(doc):
                drafts.append(
                    ChunkDraft(len(drafts), d.title, d.heading, d.text, d.tokens, d.anchor)
                )
        if not drafts:
            raise ParseError("No text found to index")
        vectors, model = await _embed(container, source.org_id, drafts)
    except (ParseError, fetching.FetchError) as exc:
        await _fail(container, source_id, str(exc))
        return
    except ProviderError as exc:
        if not ctx.last_attempt and exc.retryable:
            raise jobs.RetryLaterError(str(exc)) from exc
        await _fail(container, source_id, f"Embedding failed: {exc}")
        return

    async with ctx.fenced() as session:
        source = await session.get(Source, source_id, with_for_update=True)
        if source is None:
            return
        version = source.version + 1
        await session.execute(delete(Chunk).where(Chunk.source_id == source.id))
        for draft, vector in zip(drafts, vectors, strict=True):
            anchor = draft.anchor
            url = (
                anchor
                if anchor and anchor.startswith("http")
                else (f"{url_base}{anchor}" if url_base and anchor else url_base)
            )
            session.add(
                Chunk(
                    org_id=source.org_id,
                    source_id=source.id,
                    version=version,
                    ordinal=draft.ordinal,
                    title=draft.title[:300],
                    heading=(draft.heading or None) and draft.heading[:300],
                    url=url,
                    text=draft.text,
                    tokens=draft.tokens,
                    embedding=vector,
                    dims=len(vector),
                    embed_model=model,
                )
            )
        if source.kind != "file" and docs and source.title == source.url:
            source.title = docs[0].title[:300] or source.title
        source.version = version
        source.status = "ready"
        source.chunk_count = len(drafts)
        source.pages = sum(max(d.pages, 1) for d in docs)
        source.last_indexed_at = _now()
        await bump_kb_version(session, source.org_id)


async def _fail(container: Container, source_id: uuid.UUID, error: str) -> None:
    async with container.db.sessionmaker() as session:
        await session.execute(
            update(Source).where(Source.id == source_id).values(status="failed", error=error[:2000])
        )
        await session.commit()


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:100] or "article"


async def _unique_slug(
    session: AsyncSession, org_id: uuid.UUID, title: str, exclude: uuid.UUID | None
) -> str:
    base = slugify(title)
    slug, n = base, 2
    while True:
        stmt = select(Article.id).where(Article.org_id == org_id, Article.slug == slug)
        if exclude is not None:
            stmt = stmt.where(Article.id != exclude)
        if await session.scalar(stmt) is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


async def save_article(
    session: AsyncSession,
    actor: Actor,
    *,
    title: str,
    body: str,
    category: str | None,
    status: str,
    article_id: uuid.UUID | None = None,
    gap_id: uuid.UUID | None = None,
) -> Article:
    if status not in ("draft", "published"):
        raise AppError("Status is draft or published", code="invalid_status")
    if article_id is None:
        article = Article(
            org_id=actor.org_id,
            title=title,
            body=body,
            category=category,
            status="draft",
            created_by=actor.id,
            slug=await _unique_slug(session, actor.org_id, title, None),
        )
        session.add(article)
        await session.flush()
    else:
        found = await session.get(Article, article_id)
        if found is None or found.org_id != actor.org_id:
            raise NotFoundError("Article not found")
        article = found
        if title != article.title:
            article.slug = await _unique_slug(session, actor.org_id, title, article.id)
        article.title, article.body, article.category = title, body, category
    was_published = article.status == "published"
    article.status = status
    if status == "published":
        article.published_at = article.published_at or _now()
        await jobs.enqueue(
            session, INDEX_ARTICLE, {"article_id": str(article.id)}, org_id=actor.org_id
        )
    elif was_published:
        await session.execute(delete(Chunk).where(Chunk.article_id == article.id))
        await bump_kb_version(session, actor.org_id)
    if gap_id is not None and status == "published":
        from supportdesk.gaps.service import close_with_article

        await close_with_article(session, actor.scope, gap_id, article.id)
    audit(session, actor, "kb.article_saved", "article", article.id, status=status)
    await session.commit()
    return article


async def delete_article(session: AsyncSession, actor: Actor, article_id: uuid.UUID) -> None:
    article = await session.get(Article, article_id)
    if article is None or article.org_id != actor.org_id:
        raise NotFoundError("Article not found")
    published = article.status == "published"
    await session.delete(article)
    if published:
        await bump_kb_version(session, actor.org_id)
    audit(session, actor, "kb.article_deleted", "article", article_id)
    await session.commit()


@jobs.handles(INDEX_ARTICLE)
async def index_article(ctx: jobs.JobContext) -> None:
    from supportdesk.knowledge.parsing import parse_markdown

    container = ctx.container
    article_id = uuid.UUID(ctx.payload["article_id"])
    async with container.db.sessionmaker() as session:
        article = await session.get(Article, article_id)
        if article is None or article.status != "published":
            return
        org_id, title, body, slug = article.org_id, article.title, article.body, article.slug
        org_slug = await session.scalar(select(Org.slug).where(Org.id == org_id)) or ""
    try:
        doc = parse_markdown(body, title)
    except ParseError:
        doc = Document(title=title, sections=[Section(None, body or title)])
    doc.title = title
    drafts = chunk_document(doc)
    try:
        vectors, model = await _embed(container, org_id, drafts)
    except ProviderError as exc:
        raise jobs.RetryLaterError(str(exc)) from exc
    url = f"{container.settings.public_url}/help/{org_slug}/articles/{slug}"
    async with ctx.fenced() as session:
        current = await session.get(Article, article_id, with_for_update=True)
        if current is None or current.status != "published":
            return  # unpublished or deleted while it was being embedded
        if (current.title, current.body) != (title, body):
            return  # edited meanwhile: the job queued by that edit indexes the new text
        await session.execute(delete(Chunk).where(Chunk.article_id == article_id))
        for draft, vector in zip(drafts, vectors, strict=True):
            session.add(
                Chunk(
                    org_id=org_id,
                    article_id=article_id,
                    ordinal=draft.ordinal,
                    title=title[:300],
                    heading=draft.heading,
                    url=url,
                    text=draft.text,
                    tokens=draft.tokens,
                    embedding=vector,
                    dims=len(vector),
                    embed_model=model,
                )
            )
        await bump_kb_version(session, org_id)
