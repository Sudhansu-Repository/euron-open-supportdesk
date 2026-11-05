variable "name_prefix" {
  description = "Deployment prefix, e.g. \"supportdesk-prod\". At most 24 characters, so target group names stay unique within AWS's 32-character limit."
  type        = string
  validation {
    condition     = length(var.name_prefix) <= 24
    error_message = "name_prefix must be at most 24 characters."
  }
}

variable "vpc_id" {
  description = "VPC of the load balancer and the tasks."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the load balancer."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnets the tasks run in."
  type        = list(string)
}

variable "hostname" {
  description = "Public host name of the app and API, e.g. support.example.com. The certificate must cover it."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate (same region) for the HTTPS listener, covering hostname."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone to create the hostname alias record in. Null: point DNS at alb_dns_name yourself."
  type        = string
  default     = null
}

variable "api_image" {
  description = "Full api image reference (also runs the worker and migrate), e.g. <registry>/supportdesk-prod/api:<tag>."
  type        = string
}

variable "migrate_image" {
  description = "Image for the one-off migrate task. Null: api_image. A deploy sets it to the new release first, migrates, then moves the services (scripts/aws-deploy.sh)."
  type        = string
  default     = null
}

variable "web_image" {
  description = "Full web image reference, e.g. <registry>/supportdesk-prod/web:<tag>."
  type        = string
}

variable "container_port" {
  description = "Port every container listens on (PORT)."
  type        = number
  default     = 8080
}

variable "environment" {
  description = "Plain environment for api, worker and migrate (PORT, PUBLIC_URL, PUBLIC_API_URL, OBJECTS_BUCKET, HTTP_KEEP_ALIVE_S, WORKER_METRICS_PORT and MODEL_CACHE_DIR are set by the module). Never secrets."
  type        = map(string)
  default     = {}
}

variable "web_environment" {
  description = "Plain environment for web (PORT, HOSTNAME, API_URL and API_INTERNAL_URL are set by the module). Never secrets."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secrets injected into api, worker and migrate: [{ name, valueFrom = \"<secret arn>:<json key>::\" }] (secrets module ecs_secrets)."
  type        = list(object({ name = string, valueFrom = string }))
  default     = []
}

variable "migrate_secrets" {
  description = "Extra secrets for the one-off migrate task only (secrets module bootstrap_secrets: SUPPORTDESK_OWNER_PASSWORD for create-owner)."
  type        = list(object({ name = string, valueFrom = string }))
  default     = []
}

variable "kms_key_arn" {
  description = "CMK that seals provider API keys and webhook secrets, encrypts the objects bucket and the injected secrets."
  type        = string
}

variable "objects_bucket_arn" {
  description = "Objects bucket (storage module bucket_arn)."
  type        = string
}

variable "objects_bucket_name" {
  description = "Objects bucket name (storage module bucket_name), passed as OBJECTS_BUCKET."
  type        = string
}

variable "db_security_group_id" {
  description = "Database security group; api, worker and migrate get ingress on it."
  type        = string
}

variable "db_port" {
  description = "Database port."
  type        = number
  default     = 5432
}

variable "cache_security_group_id" {
  description = "Cache security group; api, worker and migrate get ingress on it."
  type        = string
}

variable "cache_port" {
  description = "Cache port."
  type        = number
  default     = 6379
}

variable "log_group_names" {
  description = "CloudWatch log group per app: { api, worker, web, migrate } (observability module log_group_names)."
  type        = map(string)
  validation {
    condition     = alltrue([for k in ["api", "worker", "web", "migrate"] : contains(keys(var.log_group_names), k)])
    error_message = "log_group_names needs api, worker, web and migrate."
  }
}

variable "logs_kms_key_arn" {
  description = "CMK for the WAF log group. Null uses CloudWatch's default encryption."
  type        = string
  default     = null
}

variable "cpu_architecture" {
  description = "ARM64 (Graviton, cheaper) or X86_64. Images must be built for it."
  type        = string
  default     = "ARM64"
}

variable "container_insights" {
  description = "ECS Container Insights: enabled, enhanced or disabled."
  type        = string
  default     = "enabled"
}

variable "api_cpu" {
  description = "Fargate CPU units per api task."
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Fargate memory (MiB) per api task."
  type        = number
  default     = 2048
}

variable "api_min_count" {
  description = "Minimum (and initial) api task count."
  type        = number
  default     = 2
}

variable "api_max_count" {
  description = "Maximum api task count under autoscaling. Equal to api_min_count disables scaling."
  type        = number
  default     = 6
}

variable "worker_cpu" {
  description = "Fargate CPU units per worker task."
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Fargate memory (MiB) per worker task. The local embedding model needs about 600 MiB on top of the worker."
  type        = number
  default     = 2048
}

variable "worker_min_count" {
  description = "Minimum (and initial) worker task count."
  type        = number
  default     = 1
}

variable "worker_max_count" {
  description = "Maximum worker task count under CPU autoscaling (AI turns and indexing are CPU bound). Equal to worker_min_count disables scaling."
  type        = number
  default     = 4
  validation {
    condition     = var.worker_max_count >= 1
    error_message = "worker_max_count must be at least 1."
  }
}

variable "web_cpu" {
  description = "Fargate CPU units per web task."
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Fargate memory (MiB) per web task."
  type        = number
  default     = 1024
}

variable "web_min_count" {
  description = "Minimum (and initial) web task count."
  type        = number
  default     = 1
}

variable "web_max_count" {
  description = "Maximum web task count under autoscaling."
  type        = number
  default     = 3
}

variable "cpu_target_percent" {
  description = "Average CPU the autoscaler aims for (api, worker and web)."
  type        = number
  default     = 60
}

variable "idle_timeout" {
  description = "Load balancer idle timeout in seconds. WebSockets are pinged inside it, so this only reaps abandoned connections. The api's HTTP keep-alive is set 10 s above it."
  type        = number
  default     = 300
  validation {
    condition     = var.idle_timeout >= 60 && var.idle_timeout <= 4000
    error_message = "idle_timeout must be between 60 and 4000 seconds."
  }
}

variable "deletion_protection" {
  description = "Block accidental deletion of the load balancer."
  type        = bool
  default     = true
}

variable "access_logs_bucket" {
  description = "Existing bucket for load balancer access logs (needs the ELB log-delivery bucket policy). Null disables."
  type        = string
  default     = null
}

variable "metrics_allowed_cidrs" {
  description = "Source CIDRs allowed to read /metrics through the load balancer. Empty: /metrics answers 404 at the edge."
  type        = list(string)
  default     = []
}

variable "enable_waf" {
  description = "Attach a WAF web ACL (managed rule sets plus a per-IP flood guard) to the load balancer."
  type        = bool
  default     = true
}

variable "waf_rate_limit_per_5min" {
  description = "Requests per source IP per 5 minutes before WAF blocks. Keep it high: SDK backends often sit behind one NAT address."
  type        = number
  default     = 20000
}

variable "waf_log_retention_days" {
  description = "WAF log retention."
  type        = number
  default     = 30
}

variable "worker_metrics_cidrs" {
  description = "Source CIDRs (an in-VPC Prometheus) allowed to scrape the worker's /metrics. Empty: the worker has no ingress at all (its health check probes /metrics from inside the task)."
  type        = list(string)
  default     = []
}

variable "worker_metrics_port" {
  description = "Port the worker serves /metrics on; must match WORKER_METRICS_PORT (default 9464)."
  type        = number
  default     = 9464
}

variable "ai_egress" {
  description = "Extra egress from the api and worker tasks for a self-hosted model not on HTTPS 443, as { cidr, port } pairs (for example Ollama on 11434 or vLLM inside the VPC). Empty: HTTPS only."
  type = list(object({
    cidr = string
    port = number
  }))
  default = []
}

# A boolean, not a null check on the policy: the policy is unknown until apply, and count
# must be decidable at plan time.
variable "send_mail" {
  description = "Attach mail_policy_json to the api and worker task roles (ticket mail through SES)."
  type        = bool
  default     = false
}

variable "mail_policy_json" {
  description = "IAM policy for sending mail (email module send_policy_json), with send_mail."
  type        = string
  default     = null
}
