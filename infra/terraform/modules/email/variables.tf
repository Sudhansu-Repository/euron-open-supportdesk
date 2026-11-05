variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "domain" {
  description = "Domain mail is sent from and received on (an SES domain identity), e.g. support.example.com."
  type        = string
}

variable "from_address" {
  description = "The only From address the api and worker may send as (MAIL_FROM_ADDRESS), e.g. help@support.example.com."
  type        = string
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.from_address))
    error_message = "from_address must be an email address."
  }
}

variable "route53_zone_id" {
  description = "Hosted zone that receives the DKIM records. Null: create them yourself (dkim_records output)."
  type        = string
  default     = null
}

variable "enable_inbound" {
  description = "Receive mail on the domain with SES: store it under inbound/ in the objects bucket and post it to inbound_url through SNS. Needs objects_bucket_name, inbound_url and kms_key_arn; the storage module needs allow_ses_inbound."
  type        = bool
  default     = false
}

variable "inbound_recipients" {
  description = "Addresses or domains the receipt rule accepts. Empty: the whole domain (inbox addresses and ticket reply addresses)."
  type        = list(string)
  default     = []
}

variable "inbound_url" {
  description = "HTTPS inbound URL of the email inbox (Settings > Inboxes, shown once when the token is rotated): https://<host>/api/v1/channels/email/inbound/<token>. It contains a secret."
  type        = string
  default     = null
  sensitive   = true
  validation {
    condition     = var.inbound_url == null || can(regex("^https://", var.inbound_url))
    error_message = "inbound_url must be an https:// URL."
  }
}

variable "objects_bucket_name" {
  description = "Objects bucket that keeps raw inbound mail under inbound/ (storage module bucket_name), with enable_inbound."
  type        = string
  default     = null
}

variable "kms_key_arn" {
  description = "CMK for the inbound SNS topic (the kms module's key policy lets SES use it), with enable_inbound."
  type        = string
  default     = null
}
