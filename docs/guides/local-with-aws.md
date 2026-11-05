# Local stack against real AWS

`make up` runs everything against Floci, so no AWS account is needed. To check that S3 and
KMS behave the same for real, run the local containers against real AWS resources:
Postgres, Redis, Mailpit, the mock AI, the web app and the demo site stay local; the API,
the worker and the migrate task use a real bucket and a real KMS key.

## Steps

1. Create the resources, for example with the `aws-dev` environment
   ([deploy-aws.md](deploy-aws.md)), or use an existing bucket and key your profile can use
   (`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `kms:Encrypt`, `kms:Decrypt`).
2. Copy and fill the overlay's settings from `terraform output`:

   ```bash
   cp deploy/compose/.env.aws.example deploy/compose/.env.aws
   # AWS_REGION, AWS_PROFILE (optional), OBJECTS_BUCKET, KMS_KEY_ID
   ```

3. Start:

   ```bash
   make up-aws
   make demo
   ```

`deploy/compose/compose.aws.yaml` sets `SUPPORTDESK_CLOUD=aws`, `STORAGE=s3`,
`KEY_MODE=kms`, and mounts `~/.aws` read-only into the api, worker and migrate containers.
Credentials come from your AWS profile; no static key is written to any file. Nothing
else changes in the application: the same code paths run as on Floci and on ECS.

## What to expect

- Knowledge uploads and email attachments land in the real bucket under `orgs/<org id>/`.
- AI provider keys, webhook secrets and identity secrets are sealed with the real key,
  with an encryption context per record (visible in CloudTrail).
- Mail still goes to Mailpit (`MAIL_BACKEND=smtp` from `compose.yaml`; values in the
  service `environment` take precedence over `.env.aws`). SES sending is exercised by the
  unit tests and on ECS.

## Clean up

`make down` stops the local containers. The bucket objects and the key stay in your
account; delete them there (or `terraform destroy` the environment) when done.
