output "secret_arn" {
  description = "ARN of the JSON secret holding SESSION_SECRET and TOKEN_PEPPER."
  value       = aws_secretsmanager_secret.app.arn
}

output "connections_secret_arn" {
  description = "ARN of the JSON secret holding DATABASE_URL and REDIS_URL (null without include_connection_urls)."
  value       = var.include_connection_urls ? aws_secretsmanager_secret.connections[0].arn : null
}

output "bootstrap_secret_arn" {
  description = "ARN of the JSON secret holding SUPPORTDESK_OWNER_PASSWORD (scripts/aws-run-task.sh writes and scrubs it)."
  value       = aws_secretsmanager_secret.bootstrap.arn
}

output "keys" {
  description = "Every environment variable the secrets provide to api, worker and migrate."
  value       = sort(concat(local.app_keys, local.connection_keys))
}

output "ecs_secrets" {
  description = "ECS `secrets` entries for api, worker and migrate: [{ name, valueFrom = \"<arn>:<key>::\" }]."
  value       = local.ecs_secrets
}

output "bootstrap_secrets" {
  description = "ECS `secrets` entries for the migrate task only (SUPPORTDESK_OWNER_PASSWORD)."
  value       = local.bootstrap_secrets
}
