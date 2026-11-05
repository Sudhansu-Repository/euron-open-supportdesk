# `observability` module

Logs, alarms and a dashboard for one deployment.

- A KMS-encrypted log group per app: api, worker, web, migrate.
- Metrics extracted from the worker's JSON logs: `JobFailures` (`job failed`) and `AiTurnsFailed` (an AI turn that died after every retry and was handed to a human).
- Alarms to a KMS-encrypted SNS topic (optionally e-mailed): load balancer and per-target 5xx, unhealthy targets, a service with no running task (`treat_missing_data = breaching`), api p95 latency, CPU and memory per service, database CPU, storage and connections, cache memory and CPU, failing jobs and dead AI turns.
- One dashboard with the same signals.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `log_retention_days` | CloudWatch log retention for the app log groups. | `number` | `30` |
| `logs_kms_key_arn` | CMK for the log groups (its key policy must allow CloudWatch Logs, as the kms module's does). Null uses CloudWatch's default encryption. | `string` | `null` |
| `alarm_email` | Address subscribed to alarm notifications (confirm the e-mail AWS sends). Null: subscribe something else to the topic. | `string` | `null` |
| `alb_arn_suffix` | Load balancer ARN suffix. | `string` | required |
| `ecs_cluster_name` | ECS cluster name. | `string` | required |
| `lb_services` | Load-balanced services (service module `services`): { api = { service_name, target_group_arn_suffix }, web = { ... } }. Must contain api. | `map(object({ service_name = string target_group_arn_suffix = string }))` | required |
| `ecs_services` | Every ECS service to watch for CPU and memory (service module `service_names`): { api = "api", worker = "worker", web = "web" }. | `map(string)` | required |
| `db_instance_identifier` | RDS instance identifier. | `string` | required |
| `db_max_connections` | Connection ceiling the alarm measures against. | `number` | `200` |
| `cache_replication_group_id` | ElastiCache replication group id; nodes are <id>-001, <id>-002, ... | `string` | required |
| `cache_node_count` | Nodes in the replication group (cache module num_cache_clusters). | `number` | `1` |
| `target_5xx_threshold` | 5xx responses per 5 minutes (per app, and at the load balancer) that raise an alarm. | `number` | `25` |
| `api_p95_latency_seconds` | api p95 time to first byte that raises an alarm. AI turns are queued, never on a request path. | `number` | `3` |
| `job_failed_log_pattern` | CloudWatch Logs JSON filter matching the worker's `job failed` line. | `string` | `"{ $.msg = \"job failed\" }"` |
| `ai_turn_failed_log_pattern` | CloudWatch Logs JSON filter matching the worker's line for an AI turn that died and was handed to a human. | `string` | `"{ $.msg = \"AI turn failed, handed over\" }"` |
| `job_failure_threshold` | Failed jobs per 5 minutes that raise an alarm. | `number` | `10` |
| `ai_turn_failure_threshold` | AI turns handed to humans after failing, per 5 minutes, that raise an alarm. | `number` | `3` |
| `sns_kms_key_arn` | CMK for the alarm topic (its key policy must let CloudWatch use it, as the kms module's does). | `string` | required |

## Outputs

| Name | Description |
|---|---|
| `log_group_names` | Log group per app: { api, worker, web, migrate } (service module log_group_names). |
| `alarm_topic_arn` | SNS topic receiving every alarm. |
| `dashboard_name` | CloudWatch dashboard. |
| `metrics_namespace` | Namespace of the metrics extracted from the worker logs. |
