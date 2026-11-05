variable "endpoint" {
  description = "Emulator endpoint. http://floci:4566 inside compose, http://localhost:4866 from the host."
  type        = string
  default     = "http://localhost:4866"
}

variable "name_prefix" {
  description = "Must match OBJECTS_BUCKET (<name_prefix>-objects) and KMS_KEY_ID (alias/<name_prefix>) in deploy/compose/compose.floci.yaml."
  type        = string
  default     = "supportdesk-local"
}

variable "cors_origins" {
  description = "App origins allowed to fetch objects with JavaScript."
  type        = list(string)
  default     = ["http://localhost:4810", "http://127.0.0.1:4810"]
}

variable "mail_domain" {
  description = "SES domain identity created on the emulator (MAIL_REPLY_DOMAIN locally)."
  type        = string
  default     = "supportdesk.local"
}

variable "mail_from_address" {
  description = "From address the send policy allows (MAIL_FROM_ADDRESS locally)."
  type        = string
  default     = "support@supportdesk.local"
}
