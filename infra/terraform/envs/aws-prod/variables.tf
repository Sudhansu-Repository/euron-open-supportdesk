variable "region" {
  description = "AWS region."
  type        = string
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "prod"
}

variable "extra_tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}

variable "name_prefix" {
  description = "Prefix for every resource name (at most 24 characters); the objects bucket name derives from it, so make it globally unique (e.g. \"acme-supportdesk-prod\")."
  type        = string
}

variable "hostname" {
  description = "Public host name of the app and API, e.g. support.example.com."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate in the same region covering hostname."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the alias record and the DKIM records. Null: create them yourself (load_balancer_dns_name and dkim_records outputs)."
  type        = string
  default     = null
}

variable "mail_domain" {
  description = "Domain ticket mail is sent from and replies come back to (an SES domain identity; MAIL_REPLY_DOMAIN), e.g. support.example.com."
  type        = string
}

variable "mail_from_address" {
  description = "From address of ticket mail, on mail_domain (MAIL_FROM_ADDRESS), e.g. help@support.example.com."
  type        = string
}

variable "mail_from_name" {
  description = "Display name on outgoing mail (MAIL_FROM_NAME)."
  type        = string
  default     = "Support"
}

variable "enable_inbound_email" {
  description = "Receive customer email with SES on mail_domain and post it to inbound_email_url (see the email module)."
  type        = bool
  default     = false
}

variable "inbound_email_recipients" {
  description = "Addresses or domains SES accepts for SupportDesk. Empty: all of mail_domain."
  type        = list(string)
  default     = []
}

variable "inbound_email_url" {
  description = "The email inbox's inbound URL (Settings > Inboxes, shown once): https://<hostname>/api/v1/channels/email/inbound/<token>. Needed with enable_inbound_email."
  type        = string
  default     = null
  sensitive   = true
}

variable "image_tag" {
  description = "Image tag the api, worker and web services run (the git commit or a release)."
  type        = string
}

variable "migrate_image_tag" {
  description = "Image tag of the one-off migrate task. Null: image_tag. scripts/aws-deploy.sh sets it to the new release while the services stay on the old one, migrates, then moves the services."
  type        = string
  default     = null
}

variable "alarm_email" {
  description = "Alarm notification address."
  type        = string
  default     = null
}

variable "api_extra_environment" {
  description = "Extra api, worker and migrate environment (see docs/guides/configuration.md). Never secrets."
  type        = map(string)
  default     = {}
}

variable "backup_retention_days" {
  description = "Days a database backup in the objects bucket (backups/) is kept."
  type        = number
  default     = 35
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "metrics_allowed_cidrs" {
  description = "Source CIDRs allowed to scrape the api's /metrics through the load balancer."
  type        = list(string)
  default     = []
}

variable "worker_metrics_cidrs" {
  description = "In-VPC Prometheus CIDRs allowed to scrape the worker's /metrics on port 9464. Empty: no worker ingress."
  type        = list(string)
  default     = []
}

variable "ai_egress" {
  description = "Extra api and worker egress for a self-hosted model not on HTTPS 443 (Ollama, vLLM), as { cidr, port } pairs. Also allows private AI endpoints."
  type = list(object({
    cidr = string
    port = number
  }))
  default = []
}
