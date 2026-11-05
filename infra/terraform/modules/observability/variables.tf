variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the app log groups."
  type        = number
  default     = 30
}

variable "logs_kms_key_arn" {
  description = "CMK for the log groups (its key policy must allow CloudWatch Logs, as the kms module's does). Null uses CloudWatch's default encryption."
  type        = string
  default     = null
}

variable "alarm_email" {
  description = "Address subscribed to alarm notifications (confirm the e-mail AWS sends). Null: subscribe something else to the topic."
  type        = string
  default     = null
}

variable "alb_arn_suffix" {
  description = "Load balancer ARN suffix."
  type        = string
}

variable "ecs_cluster_name" {
  description = "ECS cluster name."
  type        = string
}

variable "lb_services" {
  description = "Load-balanced services (service module `services`): { api = { service_name, target_group_arn_suffix }, web = { ... } }. Must contain api."
  type = map(object({
    service_name            = string
    target_group_arn_suffix = string
  }))
  validation {
    condition     = contains(keys(var.lb_services), "api")
    error_message = "lb_services must contain api."
  }
}

variable "ecs_services" {
  description = "Every ECS service to watch for CPU and memory (service module `service_names`): { api = \"api\", worker = \"worker\", web = \"web\" }."
  type        = map(string)
}

variable "db_instance_identifier" {
  description = "RDS instance identifier."
  type        = string
}

variable "db_max_connections" {
  description = "Connection ceiling the alarm measures against."
  type        = number
  default     = 200
}

variable "cache_replication_group_id" {
  description = "ElastiCache replication group id; nodes are <id>-001, <id>-002, ..."
  type        = string
}

variable "cache_node_count" {
  description = "Nodes in the replication group (cache module num_cache_clusters)."
  type        = number
  default     = 1
}

variable "target_5xx_threshold" {
  description = "5xx responses per 5 minutes (per app, and at the load balancer) that raise an alarm."
  type        = number
  default     = 25
}

variable "api_p95_latency_seconds" {
  description = "api p95 time to first byte that raises an alarm. AI turns are queued, never on a request path."
  type        = number
  default     = 3
}

variable "job_failed_log_pattern" {
  description = "CloudWatch Logs JSON filter matching the worker's `job failed` line."
  type        = string
  default     = "{ $.msg = \"job failed\" }"
}

variable "ai_turn_failed_log_pattern" {
  description = "CloudWatch Logs JSON filter matching the worker's line for an AI turn that died and was handed to a human."
  type        = string
  default     = "{ $.msg = \"AI turn failed, handed over\" }"
}

variable "job_failure_threshold" {
  description = "Failed jobs per 5 minutes that raise an alarm."
  type        = number
  default     = 10
}

variable "ai_turn_failure_threshold" {
  description = "AI turns handed to humans after failing, per 5 minutes, that raise an alarm."
  type        = number
  default     = 3
}

variable "sns_kms_key_arn" {
  description = "CMK for the alarm topic (its key policy must let CloudWatch use it, as the kms module's does)."
  type        = string
}
