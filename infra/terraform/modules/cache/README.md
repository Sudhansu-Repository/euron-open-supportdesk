# `cache` module

ElastiCache (Valkey by default) for what api and worker replicas share: pub/sub fan-out of live updates to every replica holding a WebSocket, the exact answer cache, AI budget counters, rate limits and cache generation numbers.

- Jobs never live here (they are Postgres rows), so losing Redis costs live fan-out and cache hits, never a message.
- `maxmemory-policy` is `volatile-lru` and validated to never evict keys without a TTL: cache entries and rate windows may go under memory pressure, counters and generation numbers stay.
- TLS in transit, AUTH token (in Secrets Manager, handed to the secrets module inside `REDIS_URL`), at-rest encryption with the CMK, slow log to CloudWatch, Multi-AZ failover with two or more nodes.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `vpc_id` | VPC id. | `string` | required |
| `subnet_ids` | Private subnets for the cache subnet group (2+ AZs for failover). | `list(string)` | required |
| `kms_key_arn` | CMK for data at rest and for the AUTH token secret. | `string` | required |
| `logs_kms_key_arn` | CMK for the slow-log group. Null uses CloudWatch's default encryption. | `string` | `null` |
| `engine` | valkey (default, cheaper) or redis. | `string` | `"valkey"` |
| `engine_version` | Engine version, e.g. 8.0 for Valkey or 7.1 for Redis OSS. | `string` | `"8.0"` |
| `parameter_group_family` | Parameter group family matching engine and engine_version, e.g. valkey8 or redis7. | `string` | `"valkey8"` |
| `maxmemory_policy` | Eviction policy. volatile-lru evicts only keys with a TTL (cache entries, rate windows) and never the counters without one (cache generations, budgets); noeviction refuses writes when full instead. | `string` | `"volatile-lru"` |
| `node_type` | Node type. Graviton (t4g/m7g/r7g) recommended. | `string` | `"cache.t4g.small"` |
| `num_cache_clusters` | Nodes in the replication group: 1 (no failover) or 2+ (primary plus replicas, Multi-AZ failover). | `number` | `2` |
| `snapshot_retention_days` | Daily snapshots kept (0 disables). Counters rehydrate from Postgres, so snapshots only speed up recovery. | `number` | `1` |
| `recovery_window_in_days` | Days a deleted AUTH token secret stays recoverable. 0 deletes immediately. | `number` | `30` |
| `log_retention_days` | Slow-log retention in CloudWatch Logs. | `number` | `30` |
| `apply_immediately` | Apply modifications now instead of in the maintenance window. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `primary_endpoint_address` | Primary endpoint hostname. |
| `replication_group_id` | Replication group id (CloudWatch dimension prefix). |
| `member_clusters` | Node ids (CloudWatch CacheClusterId dimension). |
| `security_group_id` | Cache security group; consumers add ingress rules against it. |
| `auth_secret_arn` | Secrets Manager secret holding AUTH_TOKEN and REDIS_URL. |
| `connection_url` | REDIS_URL for the API (rediss://, TLS + AUTH). Pass it to the secrets module, never to plain task environment. |
