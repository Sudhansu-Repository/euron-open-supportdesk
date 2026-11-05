# `service` module

The application plane on ECS Fargate behind one Application Load Balancer (with WAF):

| App | Role | Exposure |
|---|---|---|
| `api` | REST API (`/api/*`), WebSockets (`/ws/*`), `/healthz`, `/readyz`, `/docs`, `/openapi.json` | ALB on `hostname`, CPU autoscaled; Cloud Map name for the web task |
| `worker` | AI turns, indexing, mail, webhooks, SLA scans, rollups | none (optional Prometheus scrape); CPU autoscaled between `worker_min_count` and `worker_max_count` |
| `web` | the Next.js app: agent app, portal, help center, `widget.js` (every other path, and `/api/healthz`) | ALB, CPU autoscaled |
| `migrate` | one-off task for `migrate`, `create-owner`, `seed-demo`; may run a newer image (`migrate_image`) so deploys migrate first | none |

The ALB idle timeout (`idle_timeout`, 300 s) bounds idle WebSockets; the api's HTTP keep-alive (`HTTP_KEEP_ALIVE_S`) is set 10 s above it. Every app: its own security group (ingress only from the ALB or named callers), its own execution and task roles (only the api, worker and migrate touch S3 and KMS; the api and worker may send mail through SES, with `send_mail`), read-only root filesystem with only the paths it writes mounted (the embedding model cache among them), ARM64, no public IP, deployment circuit breaker with rollback. WAF with AWS managed rules; the body rules that mistake uploads, Markdown and raw email for attacks only count.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Deployment prefix, e.g. "supportdesk-prod". At most 24 characters, so target group names stay unique within AWS's 32-character limit. | `string` | required |
| `vpc_id` | VPC of the load balancer and the tasks. | `string` | required |
| `public_subnet_ids` | Public subnets for the load balancer. | `list(string)` | required |
| `private_subnet_ids` | Private subnets the tasks run in. | `list(string)` | required |
| `hostname` | Public host name of the app and API, e.g. support.example.com. The certificate must cover it. | `string` | required |
| `certificate_arn` | ACM certificate (same region) for the HTTPS listener, covering hostname. | `string` | required |
| `route53_zone_id` | Hosted zone to create the hostname alias record in. Null: point DNS at alb_dns_name yourself. | `string` | `null` |
| `api_image` | Full api image reference (also runs the worker and migrate), e.g. <registry>/supportdesk-prod/api:<tag>. | `string` | required |
| `migrate_image` | Image for the one-off migrate task. Null: api_image. A deploy sets it to the new release first, migrates, then moves the services (scripts/aws-deploy.sh). | `string` | `null` |
| `web_image` | Full web image reference, e.g. <registry>/supportdesk-prod/web:<tag>. | `string` | required |
| `container_port` | Port every container listens on (PORT). | `number` | `8080` |
| `environment` | Plain environment for api, worker and migrate (PORT, PUBLIC_URL, PUBLIC_API_URL, OBJECTS_BUCKET, HTTP_KEEP_ALIVE_S, WORKER_METRICS_PORT and MODEL_CACHE_DIR are set by the module). Never secrets. | `map(string)` | `{}` |
| `web_environment` | Plain environment for web (PORT, HOSTNAME, API_URL and API_INTERNAL_URL are set by the module). Never secrets. | `map(string)` | `{}` |
| `secrets` | Secrets injected into api, worker and migrate: [{ name, valueFrom = "<secret arn>:<json key>::" }] (secrets module ecs_secrets). | `list(object({ name = string, valueFrom = string }))` | `[]` |
| `migrate_secrets` | Extra secrets for the one-off migrate task only (secrets module bootstrap_secrets: SUPPORTDESK_OWNER_PASSWORD for create-owner). | `list(object({ name = string, valueFrom = string }))` | `[]` |
| `kms_key_arn` | CMK that seals provider API keys and webhook secrets, encrypts the objects bucket and the injected secrets. | `string` | required |
| `objects_bucket_arn` | Objects bucket (storage module bucket_arn). | `string` | required |
| `objects_bucket_name` | Objects bucket name (storage module bucket_name), passed as OBJECTS_BUCKET. | `string` | required |
| `db_security_group_id` | Database security group; api, worker and migrate get ingress on it. | `string` | required |
| `db_port` | Database port. | `number` | `5432` |
| `cache_security_group_id` | Cache security group; api, worker and migrate get ingress on it. | `string` | required |
| `cache_port` | Cache port. | `number` | `6379` |
| `log_group_names` | CloudWatch log group per app: { api, worker, web, migrate } (observability module log_group_names). | `map(string)` | required |
| `logs_kms_key_arn` | CMK for the WAF log group. Null uses CloudWatch's default encryption. | `string` | `null` |
| `cpu_architecture` | ARM64 (Graviton, cheaper) or X86_64. Images must be built for it. | `string` | `"ARM64"` |
| `container_insights` | ECS Container Insights: enabled, enhanced or disabled. | `string` | `"enabled"` |
| `api_cpu` | Fargate CPU units per api task. | `number` | `1024` |
| `api_memory` | Fargate memory (MiB) per api task. | `number` | `2048` |
| `api_min_count` | Minimum (and initial) api task count. | `number` | `2` |
| `api_max_count` | Maximum api task count under autoscaling. Equal to api_min_count disables scaling. | `number` | `6` |
| `worker_cpu` | Fargate CPU units per worker task. | `number` | `1024` |
| `worker_memory` | Fargate memory (MiB) per worker task. The local embedding model needs about 600 MiB on top of the worker. | `number` | `2048` |
| `worker_min_count` | Minimum (and initial) worker task count. | `number` | `1` |
| `worker_max_count` | Maximum worker task count under CPU autoscaling (AI turns and indexing are CPU bound). Equal to worker_min_count disables scaling. | `number` | `4` |
| `web_cpu` | Fargate CPU units per web task. | `number` | `512` |
| `web_memory` | Fargate memory (MiB) per web task. | `number` | `1024` |
| `web_min_count` | Minimum (and initial) web task count. | `number` | `1` |
| `web_max_count` | Maximum web task count under autoscaling. | `number` | `3` |
| `cpu_target_percent` | Average CPU the autoscaler aims for (api, worker and web). | `number` | `60` |
| `idle_timeout` | Load balancer idle timeout in seconds. WebSockets are pinged inside it, so this only reaps abandoned connections. The api's HTTP keep-alive is set 10 s above it. | `number` | `300` |
| `deletion_protection` | Block accidental deletion of the load balancer. | `bool` | `true` |
| `access_logs_bucket` | Existing bucket for load balancer access logs (needs the ELB log-delivery bucket policy). Null disables. | `string` | `null` |
| `metrics_allowed_cidrs` | Source CIDRs allowed to read /metrics through the load balancer. Empty: /metrics answers 404 at the edge. | `list(string)` | `[]` |
| `enable_waf` | Attach a WAF web ACL (managed rule sets plus a per-IP flood guard) to the load balancer. | `bool` | `true` |
| `waf_rate_limit_per_5min` | Requests per source IP per 5 minutes before WAF blocks. Keep it high: SDK backends often sit behind one NAT address. | `number` | `20000` |
| `waf_log_retention_days` | WAF log retention. | `number` | `30` |
| `worker_metrics_cidrs` | Source CIDRs (an in-VPC Prometheus) allowed to scrape the worker's /metrics. Empty: the worker has no ingress at all (its health check probes /metrics from inside the task). | `list(string)` | `[]` |
| `worker_metrics_port` | Port the worker serves /metrics on; must match WORKER_METRICS_PORT (default 9464). | `number` | `9464` |
| `ai_egress` | Extra egress from the api and worker tasks for a self-hosted model not on HTTPS 443, as { cidr, port } pairs (for example Ollama on 11434 or vLLM inside the VPC). Empty: HTTPS only. | `list(object({ cidr = string port = number }))` | `[]` |
| `send_mail` | Attach mail_policy_json to the api and worker task roles (ticket mail through SES). | `bool` | `false` |
| `mail_policy_json` | IAM policy for sending mail (email module send_policy_json), with send_mail. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `cluster_name` | ECS cluster name. |
| `cluster_arn` | ECS cluster ARN. |
| `url` | Public URL of the app and API. |
| `internal_urls` | Private service URLs through Cloud Map: { api } (the web task's rewrite target). |
| `alb_dns_name` | Load balancer DNS name (CNAME target for the host name when the zone is not in Route53). |
| `alb_arn_suffix` | Load balancer ARN suffix, for CloudWatch metrics. |
| `services` | Load-balanced services: { api, web } => { service_name, target_group_arn_suffix }. |
| `service_names` | Every ECS service name (api, worker, web). |
| `security_group_ids` | Task security group per app. |
| `task_role_arns` | Task role per app. |
| `run_task` | Parameters for one-off tasks: `supportdesk migrate` (task_definition, the default), or `create-owner` and `seed-demo` as command overrides on the same definition. |
| `namespace_id` | Cloud Map private DNS namespace (web resolves api.<name_prefix>.internal through it). |
