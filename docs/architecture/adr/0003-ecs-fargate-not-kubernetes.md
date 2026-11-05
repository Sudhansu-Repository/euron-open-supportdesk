# ADR-0003: ECS Fargate, not Kubernetes

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The brief mentioned Kubernetes. Every Euron open-source project ships Terraform for AWS
with the same module set, and the target user (a startup or support team) wants the
fewest moving parts to operate.

## Decision

The `service` Terraform module runs the api, worker and web as ECS Fargate services
behind an Application Load Balancer (idle timeout suitable for WebSockets), with RDS
PostgreSQL (pgvector), ElastiCache, S3, KMS, Secrets Manager, SES and CloudWatch.
Migrations run as a one-off ECS task before the services roll (`make aws-deploy`).

## Consequences

**Good**
- No cluster to upgrade or secure; the same shape as the other Euron projects.
- `make tf-aws-on-floci` applies and destroys the whole `aws-dev` environment locally.

**Bad / caveats**
- No Helm chart for teams that already run Kubernetes (on the roadmap). The containers are
  ordinary images configured by environment, so a chart is a packaging task.
- A GPU Ollama service is not provisioned; self-hosted models on AWS are reached through
  `ai_egress`.

## Alternatives considered

- **EKS with a Helm chart**: more flexible, much more to operate for a support desk.
- **A single EC2 instance with Compose**: cheapest, but no rolling deploys or managed
  database.
