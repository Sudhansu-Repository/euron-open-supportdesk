variable "name_prefix" {
  description = "Prefix for every resource name. The bucket is <name_prefix>-objects."
  type        = string
}

variable "kms_key_arn" {
  description = "CMK for SSE-KMS. Null falls back to SSE-S3."
  type        = string
  default     = null
}

variable "enforce_tls" {
  description = "Deny any request not made over TLS. Disable only for an emulator that speaks plain HTTP."
  type        = bool
  default     = true
}

variable "noncurrent_retention_days" {
  description = "Days a replaced or deleted object version stays recoverable."
  type        = number
  default     = 30
  validation {
    condition     = var.noncurrent_retention_days >= 1
    error_message = "noncurrent_retention_days must be at least 1."
  }
}

variable "export_expiration_days" {
  description = "Days a report or ticket export (exports/) is kept."
  type        = number
  default     = 7
  validation {
    condition     = var.export_expiration_days >= 1
    error_message = "export_expiration_days must be at least 1."
  }
}

variable "backup_retention_days" {
  description = "Days a database backup (backups/) is kept."
  type        = number
  default     = 35
  validation {
    condition     = var.backup_retention_days >= 1
    error_message = "backup_retention_days must be at least 1."
  }
}

variable "cors_origins" {
  description = "Browser origins allowed to GET objects with JavaScript (the app URL). Empty = no CORS configuration."
  type        = list(string)
  default     = []
}

variable "force_destroy" {
  description = "Allow `terraform destroy` to delete a non-empty bucket. Never in production."
  type        = bool
  default     = false
}

variable "inbound_retention_days" {
  description = "Days raw inbound email stored by SES (inbound/) is kept; the api has parsed it into a ticket long before."
  type        = number
  default     = 30
  validation {
    condition     = var.inbound_retention_days >= 1
    error_message = "inbound_retention_days must be at least 1."
  }
}

variable "allow_ses_inbound" {
  description = "Let SES receipt rules of this account write raw inbound email under inbound/ (email module enable_inbound)."
  type        = bool
  default     = false
}
