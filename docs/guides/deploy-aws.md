# Deploy to AWS

`infra/terraform` provisions a complete AWS deployment. This repository never applies it
to a real account itself (it is validated, linted, policy-scanned and applied against
Floci by `make tf-aws-on-floci`); it is here so you can.

## What gets created

| Module | Resources |
| --- | --- |
| `network` | VPC, public and private subnets across availability zones, NAT, security groups |
| `database` | RDS PostgreSQL 16 (the `vector` extension is created by the first migration as the master user). aws-dev: single AZ, 3-day backups; aws-prod: Multi-AZ, 14-day backups, deletion protection |
| `cache` | ElastiCache (Redis-compatible) with AUTH and TLS: live event fan-out, the exact answer cache copy, rate limits |
| `storage` | The objects bucket (SSE-KMS, versioning, public access blocked): knowledge uploads, attachments, raw inbound mail |
| `kms` | A customer managed key: sealing (`KEY_MODE=kms`), the bucket, logs, the inbound SNS topic |
| `secrets` | Secrets Manager: `<prefix>/app` (`SESSION_SECRET`, `TOKEN_PEPPER`), `<prefix>/connections` (`DATABASE_URL`, `REDIS_URL`), `<prefix>/bootstrap` (the first owner's password) |
| `ecr` | Image repositories for the server and web images |
| `service` | ECS Fargate services `api`, `worker`, `web` (autoscaled; aws-dev 1 to 2 each, aws-prod 2 to 6) and a `migrate` task definition, behind an ALB (HTTPS, `/api/*` and `/ws/*` to the API, everything else to web) |
| `email` | SES domain identity with Easy DKIM, a configuration set with bounce and complaint suppression, and optionally inbound receiving to S3 plus SNS |
| `observability` | CloudWatch log groups, alarms to an SNS topic (optional email), a dashboard |

## Prerequisites

- An AWS account and credentials for it, Terraform 1.16, Docker with buildx, the AWS CLI,
  Python 3.
- A hostname and an ACM certificate for it in the same region; optionally a Route53 zone
  (otherwise create the CNAME and DKIM records yourself from the outputs).
- A mail domain verified in SES. New SES accounts can only
  send to verified addresses: request production access before replying to customers.

## Steps

```bash
cd infra/terraform/envs/aws-dev
cp terraform.tfvars.example terraform.tfvars     # name_prefix, hostname, certificate, mail domain
cp backend.tf.example backend.tf                 # optional: remote state in S3
cd -
make aws-deploy ENV=aws-dev TAG=0.1.0
SUPPORTDESK_OWNER_PASSWORD='...' make aws-admin ENV=aws-dev EMAIL=you@example.com ORG='Acme'
```

`make aws-deploy` (`scripts/aws-deploy.sh`) is **migrate first**:

1. apply the image registries and their KMS key;
2. build the server and web images (`linux/arm64` by default, `PLATFORM` to change) and
   push them with the tag;
3. apply everything else, with the services still on the tag they run now and only the
   migrate task on the new one;
4. run the migrations as a one-off ECS task, before any new code serves;
5. apply again with the new tag everywhere, so the services roll onto it;
6. wait for the services to become stable.

A failed migration stops the deploy with the previous release still serving, so
migrations must stay backward compatible with the release before them (add a column,
release, then remove the old one a release later). `make aws-migrate ENV=...` runs the
migrations alone.

`make aws-admin` stores the password in the bootstrap secret, runs `create-owner` as a
one-off task, then overwrites the secret with a random value; the password never travels
as an ECS task override. Then sign in at the `url` output.

The services run with `ENVIRONMENT=production`, so the boot guards
([security.md](../architecture/security.md#production-boot-guards)) refuse unsafe settings.
Extra non-secret settings go in `api_extra_environment` (for example
`{ WIDGET_RPM = "30", WORKER_CONCURRENCY = "8" }`).

## Inbound email with SES

1. Create or open the email inbox in Settings > Inboxes, set its address, and rotate its
   inbound token. Copy the URL shown once:
   `https://<hostname>/api/v1/channels/email/inbound/<token>`.
2. In `terraform.tfvars`: `enable_inbound_email = true`, `inbound_email_url = "<that URL>"`,
   optionally `inbound_email_recipients` (default: the whole mail domain, which covers the
   inbox address and the `<local>+<token>@<domain>` reply addresses). Use a region where
   SES receiving is available; only one receipt rule set is active per account and region.
3. Apply. SES stores each message under `inbound/` in the objects bucket and publishes it
   (Base64, up to 150 KB) to an SNS topic whose HTTPS subscription is the inbound URL. MX
   for the domain points at SES inbound (created when a Route53 zone is given; otherwise
   see the `inbound_mx_record` output).
4. The environments already set `MAIL_REPLY_DOMAIN` to `mail_domain`, so reply addresses
   come back through the same receipt rule.

The API verifies each SNS signature and confirms the subscription itself on the first
request ([channels.md](../architecture/channels.md#inbound)); check the subscription shows
`Confirmed` in the SNS console after the first deploy. Enable raw message content on the SES
receipt rule action, or the notification carries no mail.

## Choosing a model provider on AWS

| Option | How | Trade-off |
| --- | --- | --- |
| No model | Provider `extractive` (the default) | Nothing leaves the VPC; answers are quoted passages |
| A hosted API (OpenAI, Anthropic, Groq, Together) | Settings > AI with your key; reached over HTTPS through NAT | Simplest; customer text (redacted of cards and secrets) goes to the provider |
| Amazon Bedrock | Bedrock is not a native provider in 0.1.0. Put an OpenAI-compatible gateway in front of it (a LiteLLM proxy, or Euron Open TokenShield) and use the `openai` provider with that base URL | Stays inside AWS; one more service to run |
| A self-hosted model in the VPC (Ollama, vLLM on EC2 GPU) | Run it yourself (not provisioned by this Terraform), allow the egress with `ai_egress = [{ cidr = "10.0.0.0/16", port = 11434 }]`, keep `AI_ALLOW_PRIVATE_ENDPOINTS` true, use the `ollama` or `openai` provider | Full control; you operate the GPU host |

Set budgets in Settings > AI before connecting a paid provider. Embeddings run locally in
the API and worker tasks by default; size their CPU and memory for it (the model is
downloaded at start into the task's cache directory).

## Production checklist

- `aws-prod` for anything customer facing (Multi-AZ, deletion protection, 2+ tasks).
- `alarm_email` set and confirmed.
- Allowed origins set on every widget inbox.
- `SIGNUP_ENABLED=false` (in `api_extra_environment`) once your organisation exists, if the install is private.
- SES production access requested; DKIM records published.
- Backups: RDS automated backups and bucket versioning are on; test a restore
  ([operations.md](operations.md#backups-and-restore)).
