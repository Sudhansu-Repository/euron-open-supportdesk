# `email` module

Amazon SES for SupportDesk's mail, both directions.

- Outgoing: a domain identity with Easy DKIM (records in Route53 when a zone is given, otherwise in `dkim_records`), a default configuration set with bounce and complaint metrics and suppression, and an IAM policy (`send_policy_json`) that lets the api and worker send only as `from_address`.
- Incoming (`enable_inbound`): a receipt rule set (made active) whose rule stores the raw message under `inbound/` in the objects bucket and publishes it Base64 encoded (up to 150 KB) to a KMS-encrypted SNS topic with an HTTPS subscription to the inbox's inbound URL. An MX record is created in Route53 when a zone is given (`inbound_mx_record` otherwise). SES receiving exists in a subset of regions, and only one receipt rule set is active per account and region.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `domain` | Domain mail is sent from and received on (an SES domain identity), e.g. support.example.com. | `string` | required |
| `from_address` | The only From address the api and worker may send as (MAIL_FROM_ADDRESS), e.g. help@support.example.com. | `string` | required |
| `route53_zone_id` | Hosted zone that receives the DKIM records. Null: create them yourself (dkim_records output). | `string` | `null` |
| `enable_inbound` | Receive mail on the domain with SES: store it under inbound/ in the objects bucket and post it to inbound_url through SNS. Needs objects_bucket_name, inbound_url and kms_key_arn; the storage module needs allow_ses_inbound. | `bool` | `false` |
| `inbound_recipients` | Addresses or domains the receipt rule accepts. Empty: the whole domain (inbox addresses and ticket reply addresses). | `list(string)` | `[]` |
| `inbound_url` | HTTPS inbound URL of the email inbox (Settings > Inboxes, shown once when the token is rotated): https://<host>/api/v1/channels/email/inbound/<token>. It contains a secret. | `string` | `null` |
| `objects_bucket_name` | Objects bucket that keeps raw inbound mail under inbound/ (storage module bucket_name), with enable_inbound. | `string` | `null` |
| `kms_key_arn` | CMK for the inbound SNS topic (the kms module's key policy lets SES use it), with enable_inbound. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `identity_arn` | SES domain identity ARN. |
| `configuration_set_name` | SES configuration set every message goes through (bounce and complaint metrics). |
| `send_policy_json` | IAM policy for the api and worker task roles: send only as from_address, only through this identity. |
| `dkim_records` | DKIM CNAMEs to publish when no Route53 zone is given: name => value. |
| `inbound_topic_arn` | SNS topic SES publishes inbound mail to (null without enable_inbound). |
| `inbound_mx_record` | MX record the domain needs for SES receiving (already created when route53_zone_id is set; null without enable_inbound). |
