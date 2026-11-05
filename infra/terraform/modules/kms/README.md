# `kms` module

One customer-managed KMS key (annual rotation) plus alias. It seals stored secrets such as AI provider keys and webhook signing secrets before they reach Postgres (KMS `Encrypt` with EncryptionContext `supportdesk:record=<row>`, so a sealed value copied to another row fails to open) and encrypts the objects bucket, RDS, ElastiCache, Secrets Manager, SNS topics and CloudWatch logs. Usage is granted per role by IAM, scoped by `kms:EncryptionContextKeys` or `kms:ViaService`; the key policy additionally lets CloudWatch (alarm topic) and SES (inbound mail into S3 and SNS) use it for this account only.

Applied in `local-floci`: the alias `alias/supportdesk-local` is what the API uses with `KEY_MODE=kms`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The alias is alias/<name_prefix>. | `string` | required |
| `deletion_window_in_days` | Waiting period before a scheduled key deletion completes. | `number` | `30` |
| `admin_principal_arns` | IAM principals allowed to administer (not use) the key. Empty = account root only, which delegates to IAM policies. | `list(string)` | `[]` |

## Outputs

| Name | Description |
|---|---|
| `key_arn` | KMS key ARN. |
| `key_id` | KMS key id. |
| `alias_name` | Alias, usable as KMS_KEY_ID. |
