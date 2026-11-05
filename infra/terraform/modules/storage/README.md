# `storage` module

One private S3 bucket for everything too large for Postgres: knowledge uploads and attachments (`orgs/<org id>/...`), raw inbound email stored by SES (`inbound/`), exports (`exports/`) and backups (`backups/`).

- SSE-KMS with the CMK and a bucket key, versioning, public access block, `BucketOwnerEnforced`, a TLS-only bucket policy.
- Lifecycle: abort incomplete multipart uploads, expire noncurrent versions, exports, inbound mail and backups after their retention.
- With `allow_ses_inbound`, the bucket policy also lets SES receipt rules of this account write under `inbound/`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The bucket is <name_prefix>-objects. | `string` | required |
| `kms_key_arn` | CMK for SSE-KMS. Null falls back to SSE-S3. | `string` | `null` |
| `enforce_tls` | Deny any request not made over TLS. Disable only for an emulator that speaks plain HTTP. | `bool` | `true` |
| `noncurrent_retention_days` | Days a replaced or deleted object version stays recoverable. | `number` | `30` |
| `export_expiration_days` | Days a report or ticket export (exports/) is kept. | `number` | `7` |
| `backup_retention_days` | Days a database backup (backups/) is kept. | `number` | `35` |
| `cors_origins` | Browser origins allowed to GET objects with JavaScript (the app URL). Empty = no CORS configuration. | `list(string)` | `[]` |
| `force_destroy` | Allow `terraform destroy` to delete a non-empty bucket. Never in production. | `bool` | `false` |
| `inbound_retention_days` | Days raw inbound email stored by SES (inbound/) is kept; the api has parsed it into a ticket long before. | `number` | `30` |
| `allow_ses_inbound` | Let SES receipt rules of this account write raw inbound email under inbound/ (email module enable_inbound). | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Objects bucket name (OBJECTS_BUCKET). |
| `bucket_arn` | Objects bucket ARN, for IAM policies. |
