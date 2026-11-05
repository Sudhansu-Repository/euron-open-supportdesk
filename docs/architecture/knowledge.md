# Knowledge

What the AI answers from, how it gets indexed, how it is searched, and how unanswered
questions turn into new articles. Code: `apps/api/src/supportdesk/knowledge/` and
`apps/api/src/supportdesk/gaps/`.

## Sources

| Kind | How it is added | Who |
| --- | --- | --- |
| File | `POST /api/v1/knowledge/sources/upload` (multipart): PDF, DOCX, Markdown, text, HTML, or an FAQ CSV with `question` and `answer` columns | admin |
| URL | `POST /api/v1/knowledge/sources/url` with one page | admin |
| Sitemap | The same endpoint with `sitemap: true`: the sitemap's same-host pages, up to `MAX_CRAWL_PAGES` (default 50) | admin |
| Article | Written in the app (Markdown, draft or published); only published articles are indexed and public | admin |

Files are stored in object storage under `orgs/<org>/kb/<source>/<sha256>`; the row keeps
the key, size and hash. Each source shows its status (`queued`, `processing`, `ready`,
`failed`) with the reason on failure, its page and chunk counts, and can be re-indexed,
inspected chunk by chunk, or deleted (its chunks cascade and the knowledge version is
bumped, so cached answers built on it are retired).

## Parsing limits

Parsing runs in the worker, in a thread, never on the request path. Every parser is
bounded so a hostile or huge file costs a known amount of work.

| Type | Detection | Sections | Limits and refusals |
| --- | --- | --- | --- |
| Any upload | extension, then content type | | `MAX_UPLOAD_BYTES` (default 25 MB); the large body limit applies only to a valid admin or owner session, everyone else stays at `MAX_BODY_BYTES` |
| PDF | `.pdf` | One section per page with text, deep link `#page=N`; title from the PDF metadata | At most 1000 pages; password protected PDFs and PDFs with no text layer (scans) are refused with a message |
| DOCX | `.docx` | Split at `Heading` and `Title` styles; tables as `Table` sections | Damaged files refused |
| Markdown | `.md`, `.markdown` | Split at `#` to `####` headings (not inside code fences); the first `#` heading becomes the title | At most 5,000,000 characters |
| Text | `.txt` | One section | At most 5,000,000 characters |
| HTML | `.html`, `.htm`, fetched pages | `script`, `style`, `nav`, `header`, `footer`, `aside`, `form`, `svg`, `iframe` removed; `main` or `article` preferred; split at `h1` to `h4` | At most 5,000,000 characters |
| FAQ CSV | `.csv` | One atomic section per row (`Q: ...\nA: ...`), the question as the heading | At most 5000 rows; needs `question` and `answer` columns (or `q`/`a`) |
| Web page | `kind=url` or `sitemap` | as HTML (or plain text) | http(s) only; instance metadata, private and loopback addresses refused at every redirect hop and after DNS (unless `ALLOW_PRIVATE_URLS`); at most 4 redirects; 20 s timeout; body cut at `MAX_UPLOAD_BYTES`; `robots.txt` honoured for the `EuronOpenSupportDesk/0.1` user agent |

## Chunking

`knowledge/chunking.py`: sections are split on sentence boundaries into chunks of about
220 tokens (hard limit 400; an overlong "sentence" such as a table dump is cut). Each
chunk keeps its section heading and deep link, and consecutive chunks overlap by one
sentence (when it is short) so an answer spanning a boundary is still found. FAQ rows stay
whole. At most 20,000 chunks per source. The embedded text is `<title> > <heading>` plus
the chunk, so a short passage keeps its topic.

## The ingest job

`kb.ingest` (3 attempts): fetch or load, parse, chunk and embed in batches of 64, all
outside any transaction; then, in one fenced transaction, delete the source's chunks,
insert the new ones with the new `version`, set the source `ready` with its counts, and
bump the organisation's `kb_version`. Retrieval never sees a half-indexed source
(`test_reindex_replaces_chunks_atomically`). Parse and fetch errors fail the source with
the reason; a retryable embedding error retries, then fails it. `kb.article` does the same
for a published article; unpublishing or deleting a published article removes its chunks
and bumps the version.

## Hybrid retrieval

`knowledge/retrieval.py`, one call per question:

1. **Vector**: the 30 nearest chunks by cosine distance, `WHERE org_id = :org AND dims = N
   AND embed_model = :current`, ordered by `embedding::vector(N) <=> :q` so the HNSW index
   for that size is used. Skipped when the question could not be embedded or its size has
   no index.
2. **Full text**: the 30 best chunks for an OR query of the question's content words
   (sanitised to `[a-z0-9]+` lexemes, at most 24) against the weighted `search` tsvector,
   ranked by `ts_rank_cd`.
3. **Reciprocal rank fusion**: each candidate scores `sum(1 / (60 + rank))` over the two
   lists; the top `top_k` (default 5) are kept. RRF orders the union without calibrating
   two incomparable scores.
4. **Relevance**: each kept hit gets `max(calibrated cosine, coverage)` (see
   [ai-agent.md](ai-agent.md#grounding)); the hits are re-sorted by relevance, then fused
   score, so the most relevant passage leads the prompt.

Vectors find paraphrases ("I can't get in" for a passage about resetting a password); full
text finds exact terms (error codes, product names) that embeddings blur.
`test_every_source_type_becomes_searchable_and_cited` uploads one source of each type and
asks a question answered only in it.

## The playground

Knowledge > Test a question (`POST /api/v1/knowledge/test`, any agent) runs the real
engine on a question with no conversation: triage, the gate, retrieval, generation,
grounding and the decision, with the caches bypassed so every run is fresh. It returns the
action and reason codes, the answer and its citations, every retrieved passage with its
calibrated similarity, coverage and relevance, the threshold, triage, tokens, cost and
timings per step. Its model calls are recorded in the ledger (without a ticket) and count
against the budget. This is the tool for tuning `min_relevance` and finding missing
knowledge (`test_playground_shows_passages_scores_and_the_decision`).

## Knowledge gaps

A question is recorded in `gap_questions` (once per customer message) when:

- the AI had no grounded answer (`no_answer`), unless the turn was also a sensitive
  intent, which is not a knowledge gap; or
- a customer marked an AI answer unhelpful (`unhelpful`).

`gaps.cluster` (every 60 s, under an advisory lock) takes up to 200 unclustered questions
per organisation, embeds any without a vector with the deployment's local embedder, and
assigns each greedily: it joins the open or drafted gap whose centroid has the highest
calibrated similarity, if that reaches 0.6 (about 0.73 raw cosine for bge-small), else it
starts a new gap titled with the question. Centroids are running means. The Gaps page
lists gaps by frequency with example questions.

### From gap to article

1. **Draft article** (`POST /api/v1/gaps/{id}/draft`): the draft is built from the agent
   replies on the conversations behind the gap. With a chat model configured it is
   rewritten into a short help article (title plus at most 150 words, or `NO_ANSWER` when
   the replies hold no answer); with the extractive provider the replies are quoted as
   they are. The gap becomes `drafted`.
2. The agent edits and **publishes** the article with the gap id: the article is indexed,
   the knowledge version bumps, and the gap is `resolved` with a link to the article.
3. The next customer asking that question gets an AI answer citing the new article
   (`test_knowledge_gap_to_article_to_answer`).

Gaps can also be dismissed or reopened.
