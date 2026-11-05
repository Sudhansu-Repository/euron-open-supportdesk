"""Knowledge: sources, articles and the playground (agents), and the public help center."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select, text, update

from supportdesk.auth.dependencies import Admin, Agent, ApiRead
from supportdesk.channels.portal import org_by_slug
from supportdesk.core.deps import ContainerDep, SessionDep
from supportdesk.core.errors import AppError, NotFoundError
from supportdesk.core.schemas import Ack, ApiModel
from supportdesk.knowledge import service
from supportdesk.knowledge.models import Article, Chunk, Source
from supportdesk.org.service import load_settings

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
public = APIRouter(prefix="/api/v1/help", tags=["help center (public)"])


class SourceOut(ApiModel):
    id: uuid.UUID
    kind: str
    title: str
    url: str | None
    filename: str | None
    size: int
    status: str
    error: str | None
    pages: int
    chunk_count: int
    version: int
    last_indexed_at: datetime | None
    created_at: datetime


class UrlIn(ApiModel):
    url: str = Field(min_length=8, max_length=2000)
    sitemap: bool = False
    title: str | None = Field(None, max_length=300)


class ArticleIn(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    category: str | None = Field(None, max_length=64)
    status: str = "draft"
    gap_id: uuid.UUID | None = Field(None, description="Close this knowledge gap when published")


class ArticleOut(ApiModel):
    id: uuid.UUID
    title: str
    slug: str
    body: str
    category: str | None
    status: str
    published_at: datetime | None
    views: int
    helpful_yes: int
    helpful_no: int
    created_at: datetime
    updated_at: datetime


class ArticleBrief(ApiModel):
    id: uuid.UUID
    title: str
    slug: str
    category: str | None
    excerpt: str
    published_at: datetime | None


class KnowledgeStats(ApiModel):
    sources: int
    ready: int
    failed: int
    processing: int
    articles: int
    published: int
    chunks: int
    kb_version: int
    embedder: str


class PlaygroundIn(ApiModel):
    question: str = Field(min_length=2, max_length=2000)


class Passage(ApiModel):
    chunk_id: str | None
    title: str
    heading: str | None
    url: str | None
    text: str
    relevance: float
    similarity: float
    coverage: float


class PlaygroundOut(ApiModel):
    question: str
    action: str
    reasons: list[str]
    answer: str | None
    grounded: bool
    method: str | None
    citations: list[dict[str, Any]]
    passages: list[Passage]
    threshold: float
    triage: dict[str, Any]
    tokens: int
    cost_usd: Decimal
    timings_ms: dict[str, float]
    provider: str


@router.get("/stats", response_model=KnowledgeStats, summary="Knowledge base at a glance")
async def stats(actor: Agent, session: SessionDep, container: ContainerDep) -> KnowledgeStats:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM kb_sources WHERE org_id = :o) AS sources,
                  (SELECT count(*) FROM kb_sources WHERE org_id = :o AND status = 'ready') AS ready,
                  (SELECT count(*) FROM kb_sources WHERE org_id = :o AND status = 'failed') AS failed,
                  (SELECT count(*) FROM kb_sources WHERE org_id = :o AND status IN ('queued','processing')) AS processing,
                  (SELECT count(*) FROM kb_articles WHERE org_id = :o) AS articles,
                  (SELECT count(*) FROM kb_articles WHERE org_id = :o AND status = 'published') AS published,
                  (SELECT count(*) FROM kb_chunks WHERE org_id = :o) AS chunks
                """
            ),
            {"o": actor.org_id},
        )
    ).one()
    bundle = await load_settings(session, actor.org_id)
    from supportdesk.ai.registry import embedder

    return KnowledgeStats(
        **dict(row._mapping),
        kb_version=bundle.org.kb_version,
        embedder=embedder(container, bundle.ai, None).name,
    )


@router.get("/sources", response_model=list[SourceOut], summary="Knowledge sources")
async def list_sources(actor: Agent, session: SessionDep) -> list[Source]:
    rows = await session.scalars(
        select(Source).where(Source.org_id == actor.org_id).order_by(Source.created_at.desc())
    )
    return list(rows.all())


@router.post(
    "/sources/upload",
    response_model=SourceOut,
    status_code=201,
    summary="Upload a file (PDF, DOCX, Markdown, text, HTML, FAQ CSV)",
)
async def upload(
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> Source:
    data = await file.read(container.settings.max_upload_bytes + 1)
    return await service.add_file(
        container, session, actor, file.filename or "upload", file.content_type, data, title
    )


@router.post(
    "/sources/url",
    response_model=SourceOut,
    status_code=201,
    summary="Import a web page or a sitemap",
)
async def add_url(
    body: UrlIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> Source:
    return await service.add_url(container, session, actor, body.url, body.sitemap, body.title)


@router.post(
    "/sources/{source_id}/reindex", response_model=SourceOut, summary="Index a source again"
)
async def reindex(source_id: uuid.UUID, actor: Admin, session: SessionDep) -> Source:
    return await service.reindex(session, actor, source_id)


@router.delete("/sources/{source_id}", status_code=204, summary="Remove a source and its chunks")
async def delete_source(
    source_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Response:
    await service.delete_source(container, session, actor, source_id)
    return Response(status_code=204)


@router.get("/sources/{source_id}/chunks", summary="The indexed passages of a source")
async def source_chunks(
    source_id: uuid.UUID,
    actor: Agent,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    await service.get_source(session, actor.scope, source_id)
    rows = await session.execute(
        select(Chunk.id, Chunk.ordinal, Chunk.heading, Chunk.text, Chunk.tokens, Chunk.url)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.ordinal)
        .limit(limit)
    )
    return [dict(r._mapping) for r in rows]


@router.get("/articles", response_model=list[ArticleOut], summary="Articles")
async def list_articles(actor: ApiRead, session: SessionDep) -> list[Article]:
    rows = await session.scalars(
        select(Article).where(Article.org_id == actor.org_id).order_by(Article.updated_at.desc())
    )
    return list(rows.all())


@router.post("/articles", response_model=ArticleOut, status_code=201, summary="Write an article")
async def create_article(body: ArticleIn, actor: Admin, session: SessionDep) -> Article:
    return await service.save_article(
        session,
        actor,
        title=body.title,
        body=body.body,
        category=body.category,
        status=body.status,
        gap_id=body.gap_id,
    )


@router.get("/articles/{article_id}", response_model=ArticleOut, summary="An article")
async def get_article(article_id: uuid.UUID, actor: ApiRead, session: SessionDep) -> Article:
    article = await session.get(Article, article_id)
    if article is None or article.org_id != actor.org_id:
        raise NotFoundError("Article not found")
    return article


@router.put(
    "/articles/{article_id}", response_model=ArticleOut, summary="Edit or publish an article"
)
async def update_article(
    article_id: uuid.UUID, body: ArticleIn, actor: Admin, session: SessionDep
) -> Article:
    return await service.save_article(
        session,
        actor,
        title=body.title,
        body=body.body,
        category=body.category,
        status=body.status,
        article_id=article_id,
        gap_id=body.gap_id,
    )


@router.delete("/articles/{article_id}", status_code=204, summary="Delete an article")
async def delete_article(article_id: uuid.UUID, actor: Admin, session: SessionDep) -> Response:
    await service.delete_article(session, actor, article_id)
    return Response(status_code=204)


@router.post(
    "/test", response_model=PlaygroundOut, summary="Ask a test question (the real AI pipeline)"
)
async def playground(body: PlaygroundIn, actor: Agent, container: ContainerDep) -> PlaygroundOut:
    from supportdesk.ai.assist import playground as run

    return PlaygroundOut.model_validate(await run(container, actor.org_id, body.question))


# ----- public help center -----


class HelpCenter(ApiModel):
    org_name: str
    slug: str
    title: str
    accent_color: str
    widget_key: str | None
    categories: list[dict[str, Any]]
    popular: list[ArticleBrief]


def plain_excerpt(markdown: str, limit: int = 180) -> str:
    """The first words of an article as plain text: Markdown syntax removed."""
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links and images keep their text
    text = re.sub(r"[`*_>#|~]+", " ", text)
    text = re.sub(r"^\s*(?:[-+]|\d+\.)\s+", " ", text, flags=re.M)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _brief(a: Article) -> ArticleBrief:
    excerpt = plain_excerpt(a.body)
    return ArticleBrief(
        id=a.id,
        title=a.title,
        slug=a.slug,
        category=a.category,
        excerpt=excerpt,
        published_at=a.published_at,
    )


@public.get("/{slug}", response_model=HelpCenter, summary="A help center's home")
async def help_home(slug: str, session: SessionDep) -> HelpCenter:
    org = await org_by_slug(session, slug)
    bundle = await load_settings(session, org.id)
    published = Article.org_id == org.id, Article.status == "published"
    cats = await session.execute(
        select(Article.category, func.count())
        .where(*published)
        .group_by(Article.category)
        .order_by(func.count().desc())
    )
    popular = await session.scalars(
        select(Article).where(*published).order_by(Article.views.desc(), Article.title).limit(8)
    )
    from supportdesk.channels.models import Inbox

    key = await session.scalar(
        select(Inbox.public_key)
        .where(Inbox.org_id == org.id, Inbox.channel == "widget", Inbox.active.is_(True))
        .limit(1)
    )
    return HelpCenter(
        org_name=org.name,
        slug=org.slug,
        title=bundle.brand.help_center_title,
        accent_color=bundle.brand.accent_color,
        widget_key=key,
        categories=[{"name": c or "general", "count": n} for c, n in cats.tuples()],
        popular=[_brief(a) for a in popular.all()],
    )


@public.get(
    "/{slug}/articles",
    response_model=list[ArticleBrief],
    summary="Search or list published articles",
)
async def help_articles(
    slug: str,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: str | None = None,
) -> list[ArticleBrief]:
    org = await org_by_slug(session, slug)
    stmt = select(Article).where(Article.org_id == org.id, Article.status == "published")
    if category:
        stmt = stmt.where(Article.category == category)
    if q and q.strip():
        query = func.websearch_to_tsquery("english", q.strip())
        stmt = stmt.where(Article.search.op("@@")(query)).order_by(
            func.ts_rank_cd(Article.search, query).desc()
        )
    else:
        stmt = stmt.order_by(Article.title)
    return [_brief(a) for a in (await session.scalars(stmt.limit(50))).all()]


@public.get(
    "/{slug}/articles/{article_slug}", response_model=ArticleOut, summary="A published article"
)
async def help_article(
    slug: str, article_slug: str, request: Request, session: SessionDep
) -> Article:
    org = await org_by_slug(session, slug)
    article = await session.scalar(
        select(Article).where(
            Article.org_id == org.id, Article.slug == article_slug, Article.status == "published"
        )
    )
    if article is None:
        raise NotFoundError("This article does not exist or is not published")
    await session.execute(
        update(Article).where(Article.id == article.id).values(views=Article.views + 1)
    )
    await session.commit()
    return article


class HelpfulIn(ApiModel):
    helpful: bool


@public.post(
    "/{slug}/articles/{article_slug}/feedback",
    response_model=Ack,
    summary="Was this article helpful?",
)
async def help_feedback(slug: str, article_slug: str, body: HelpfulIn, session: SessionDep) -> Ack:
    org = await org_by_slug(session, slug)
    column = Article.helpful_yes if body.helpful else Article.helpful_no
    result = await session.execute(
        update(Article)
        .where(
            Article.org_id == org.id, Article.slug == article_slug, Article.status == "published"
        )
        .values({column.key: column + 1})
    )
    if not getattr(result, "rowcount", 0):
        raise AppError("This article does not exist", code="not_found")
    await session.commit()
    return Ack(message="Thanks for the feedback")
