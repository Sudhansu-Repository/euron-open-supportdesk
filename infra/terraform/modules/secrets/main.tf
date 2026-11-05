# SupportDesk's secrets, in Secrets Manager. ECS injects each JSON key into the containers
# that need it as an environment variable; the values never appear in a task definition,
# a plan diff or a log. Each consumer gets only its own keys (see the outputs).
#
# Three secrets with different lifecycles and readers:
#
#   <name_prefix>/app          SESSION_SECRET, TOKEN_PEPPER. Read by the api, the worker
#                              and the migrate task. TOKEN_PEPPER peppers the hashes of API
#                              keys, widget, portal, invitation and inbound-mail tokens.
#   <name_prefix>/connections  DATABASE_URL (it carries the generated RDS password) and
#                              REDIS_URL (with the AUTH token). Derived from the database
#                              and cache modules and kept in step with them on every apply.
#   <name_prefix>/bootstrap    SUPPORTDESK_OWNER_PASSWORD, read only by the one-off migrate
#                              task: `make aws-admin` puts the first owner's password here,
#                              runs `create-owner`, then overwrites it with a random value.
#                              The password never travels as an ECS task override (those
#                              stay readable to anyone allowed to describe the task).
#
# Generated once, then rotated out of band; Terraform never rolls them back. The values
# are distinct on purpose (the API refuses to boot in production if SESSION_SECRET equals
# TOKEN_PEPPER). Locally (Compose) the same values come from deploy/compose/.env; on AWS
# no LOCAL_MASTER_KEY is needed because stored secrets are sealed with KMS (KEY_MODE=kms).
locals {
  app_keys        = ["SESSION_SECRET", "TOKEN_PEPPER"]
  connection_keys = var.include_connection_urls ? ["DATABASE_URL", "REDIS_URL"] : []
}

resource "random_password" "this" {
  for_each = toset(concat(local.app_keys, ["SUPPORTDESK_OWNER_PASSWORD"]))
  length   = 64
  special  = false
}

resource "aws_secretsmanager_secret" "app" {
  #checkov:skip=CKV2_AWS_57:These are HMAC keys; rotation is an operator procedure (docs/guides/operations.md), not a Lambda.
  name                    = "${var.name_prefix}/app"
  description             = "SupportDesk signing secrets (sessions, token pepper)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({ for k in local.app_keys : k => random_password.this[k].result })

  # Rotation happens out of band (put a new version by hand or by pipeline). Without
  # this, the next `terraform apply` would quietly roll every secret back.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "connections" {
  #checkov:skip=CKV2_AWS_57:Derived values; they change when the database or cache module rotates its credential.
  count                   = var.include_connection_urls ? 1 : 0
  name                    = "${var.name_prefix}/connections"
  description             = "SupportDesk connection URLs (PostgreSQL with its password, Redis/Valkey with its AUTH token)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "connections" {
  count     = var.include_connection_urls ? 1 : 0
  secret_id = aws_secretsmanager_secret.connections[0].id
  secret_string = jsonencode({
    DATABASE_URL = var.database_url
    REDIS_URL    = var.redis_url
  })
}

resource "aws_secretsmanager_secret" "bootstrap" {
  #checkov:skip=CKV2_AWS_57:Holds a random placeholder except for the seconds `make aws-admin` runs create-owner; nothing to rotate.
  name                    = "${var.name_prefix}/bootstrap"
  description             = "SupportDesk first-owner password for the one-off create-owner task (random placeholder otherwise)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "bootstrap" {
  secret_id     = aws_secretsmanager_secret.bootstrap.id
  secret_string = jsonencode({ SUPPORTDESK_OWNER_PASSWORD = random_password.this["SUPPORTDESK_OWNER_PASSWORD"].result })

  # scripts/aws-run-task.sh writes and then scrubs this value.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

locals {
  # api, worker and migrate.
  ecs_secrets = concat(
    [for k in local.app_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.app.arn}:${k}::" }],
    [for k in local.connection_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.connections[0].arn}:${k}::" }],
  )
  # The migrate task only.
  bootstrap_secrets = [
    { name = "SUPPORTDESK_OWNER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.bootstrap.arn}:SUPPORTDESK_OWNER_PASSWORD::" },
  ]
}
