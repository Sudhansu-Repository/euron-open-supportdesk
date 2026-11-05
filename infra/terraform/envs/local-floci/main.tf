# ─────────────────────────────────────────────────────────────────────────────
# Local environment on the Floci AWS emulator.
#
# The modules that build production run here unchanged; only the provider endpoints
# differ. `make up` applies this automatically (the compose `terraform` one-shot)
# before migrate, api and worker start, so local development uses S3, KMS, Secrets
# Manager and SES exactly as AWS does. By hand, against a running emulator:
#
#   terraform -chdir=infra/terraform/envs/local-floci init
#   terraform -chdir=infra/terraform/envs/local-floci apply -var endpoint=http://localhost:4866
#
# Postgres (with pgvector) and Redis are plain Compose containers locally (the emulator
# does not back RDS or ElastiCache) and outgoing mail is caught by Mailpit. The network,
# database, cache, ecr, service and observability modules are exercised by aws-dev and
# aws-prod (make tf-validate, make tf-aws-on-floci).
# ─────────────────────────────────────────────────────────────────────────────

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
}

module "storage" {
  source        = "../../modules/storage"
  name_prefix   = var.name_prefix
  kms_key_arn   = module.kms.key_arn
  enforce_tls   = false # the emulator speaks plain HTTP
  force_destroy = true
  cors_origins  = var.cors_origins
}

# Generated secrets are an AWS-deployment concern; locally compose reads
# deploy/compose/.env (make env). Created here anyway so the module is exercised.
module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = 0
}

# The SES identity and configuration set production sends through. Locally the app
# sends with MAIL_BACKEND=smtp to Mailpit, so the mail is visible on port 4825.
module "email" {
  source       = "../../modules/email"
  name_prefix  = var.name_prefix
  domain       = var.mail_domain
  from_address = var.mail_from_address
}
