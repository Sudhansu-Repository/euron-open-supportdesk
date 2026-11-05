# ADR-0004: pgvector in the same Postgres, one HNSW expression index per size

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The AI retrieves passages by vector similarity and by full text, always within one
organisation, and the semantic answer cache needs nearest-neighbour search too. Each
organisation may change its embedder, and embedders produce vectors of different sizes
(384 for bge-small, 768, 1024, 1536 for common remote models).

## Decision

Store embeddings in Postgres with pgvector, in unsized `vector` columns (`kb_chunks`,
`answer_cache`, `knowledge_gaps`, `gap_questions`) with a `dims` column. The migration
creates one partial expression HNSW index per supported size:
`USING hnsw ((embedding::vector(N)) vector_cosine_ops) WHERE dims = N` for N in 384, 768,
1024 and 1536. Queries cast the same way and filter `dims = N`, `org_id` and (for chunks)
`embed_model`, so the planner uses the matching index and vectors from different
embedders are never compared.

## Consequences

**Good**
- One database, one backup, one transaction: a re-index swaps chunks and bumps the
  knowledge version atomically, and the organisation filter is plain SQL.
- Full-text search (`tsvector`, GIN) sits next to the vectors for hybrid retrieval.
- Changing embedder needs no migration, only a re-index.

**Bad / caveats**
- Sizes outside the four indexed ones fall back to full-text search only; adding a size
  is a migration.
- Very large corpora (tens of millions of chunks) would want a dedicated vector store.

## Alternatives considered

- **A separate vector database (Qdrant, Weaviate, Pinecone)**: another service to run,
  back up and keep consistent with Postgres; tenant filtering and atomic swaps get harder.
- **One sized column per embedder**: a migration for every embedder change.
- **A single index over an unsized column**: pgvector cannot index mixed sizes.
