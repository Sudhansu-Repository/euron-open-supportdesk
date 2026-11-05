# Architecture decision records

Decisions a newcomer would question, with the context and the alternatives.

| ADR | Decision |
| --- | --- |
| [0001](0001-no-langchain.md) | No LangChain: the AI pipeline is explicit code |
| [0002](0002-no-litellm-dependency.md) | No LiteLLM dependency: the OpenAI wire format covers proxies |
| [0003](0003-ecs-fargate-not-kubernetes.md) | ECS Fargate on AWS, not Kubernetes |
| [0004](0004-pgvector-in-the-same-postgres.md) | pgvector in the same Postgres, with an HNSW expression index per embedding size |
| [0005](0005-jobs-as-a-postgres-outbox.md) | Background jobs as a Postgres transactional outbox with NOTIFY and leases, not Redis Streams |
| [0006](0006-live-events-as-invalidations.md) | Live events are invalidations over Redis pub/sub or Postgres LISTEN/NOTIFY |
| [0007](0007-conversation-equals-ticket.md) | One conversation is one ticket |
| [0008](0008-policy-outside-the-model.md) | Whether an AI answer is sent is decided by code, never by the model |
| [0009](0009-local-embeddings-by-default.md) | Local embeddings by default (fastembed, bge-small) |
| [0010](0010-mit-licence.md) | MIT licence |
| [0011](0011-services-own-their-queries.md) | Domain services own their queries; tenant scoping through OrgScoped and scoped lookups |
