"""Knowledge: sources (files and web pages), articles written in the app, and the chunks
the AI retrieves from, with their embeddings."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from supportdesk.core.db import Base, OrgScoped, TimestampMixin, new_id

SOURCE_KINDS = ("file", "url", "sitemap")
SOURCE_STATUSES = ("queued", "processing", "ready", "failed")
# Dimensions with an HNSW index (see the migration): the embedders we ship produce these.
INDEXED_DIMS = (384, 768, 1024, 1536)


class Source(OrgScoped, TimestampMixin, Base):
    __tablename__ = "kb_sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bumped on every re-index; chunks of older versions are replaced atomically.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class Article(OrgScoped, TimestampMixin, Base):
    """A help center article written in the app. Published articles are public and the AI
    answers from them; drafts are neither."""

    __tablename__ = "kb_articles"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_articles_org_slug"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    helpful_yes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    helpful_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(body, '')), 'B')",
            persisted=True,
        ),
    )


Index("ix_articles_search", Article.search, postgresql_using="gin")


class Chunk(OrgScoped, Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index("ix_chunks_source", "source_id", "version"),
        Index("ix_chunks_article", "article_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_sources.id", ondelete="CASCADE")
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    heading: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(2000))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    # Unsized so the embedder can change; an expression HNSW index exists per INDEXED_DIMS.
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    dims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embed_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(heading, '')), 'A') || "
            "setweight(to_tsvector('english', text), 'B')",
            persisted=True,
        ),
    )


Index("ix_chunks_search", Chunk.search, postgresql_using="gin")
