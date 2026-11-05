# `secrets` module

Secrets Manager entries, each injected by ECS only into the containers that need it:

- `<name_prefix>/app`: `SESSION_SECRET`, `TOKEN_PEPPER` (api, worker, migrate).
- `<name_prefix>/connections` (with `include_connection_urls`): `DATABASE_URL` (it carries the generated RDS password) and `REDIS_URL` (with the AUTH token).
- `<name_prefix>/bootstrap`: `SUPPORTDESK_OWNER_PASSWORD`, injected only into the one-off migrate task. `make aws-admin` writes the first owner's password here, runs `create-owner`, then overwrites it with a random value, so the password never travels as an ECS task override.

Values are generated once and rotated out of band; Terraform never rolls them back (`ignore_changes`). No `LOCAL_MASTER_KEY` on AWS: stored secrets are sealed with KMS.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `kms_key_arn` | CMK that encrypts the secrets. Null uses the AWS-managed key. | `string` | `null` |
| `recovery_window_in_days` | Days a deleted secret stays recoverable. 0 deletes immediately (local and throwaway environments). | `number` | `30` |
| `include_connection_urls` | Create the connections secret from database_url and redis_url. false where Compose supplies them (local-floci). | `bool` | `false` |
| `database_url` | DATABASE_URL (database module connection_url), with include_connection_urls. | `string` | `null` |
| `redis_url` | REDIS_URL (cache module connection_url), with include_connection_urls. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `secret_arn` | ARN of the JSON secret holding SESSION_SECRET and TOKEN_PEPPER. |
| `connections_secret_arn` | ARN of the JSON secret holding DATABASE_URL and REDIS_URL (null without include_connection_urls). |
| `bootstrap_secret_arn` | ARN of the JSON secret holding SUPPORTDESK_OWNER_PASSWORD (scripts/aws-run-task.sh writes and scrubs it). |
| `keys` | Every environment variable the secrets provide to api, worker and migrate. |
| `ecs_secrets` | ECS `secrets` entries for api, worker and migrate: [{ name, valueFrom = "<arn>:<key>::" }]. |
| `bootstrap_secrets` | ECS `secrets` entries for the migrate task only (SUPPORTDESK_OWNER_PASSWORD). |
